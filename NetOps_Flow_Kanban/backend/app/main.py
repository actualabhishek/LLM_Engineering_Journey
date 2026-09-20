import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.auth import create_session, require_user
from app.chat import get_chat_response
from app.db import get_connection, init_db, verify_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


logger = logging.getLogger(__name__)

app = FastAPI(lifespan=lifespan)

# The packaged app is served from this same origin and needs no CORS at all.
# These are the dev servers: `next dev`, and the port the e2e suite uses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3100"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str


@app.post("/api/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE username = ?",
            (payload.username,),
        ).fetchone()
    finally:
        conn.close()

    if row is None or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return LoginResponse(token=create_session(row["id"]))


@app.get("/api/me")
def me(user_id: int = Depends(require_user)):
    conn = get_connection()
    try:
        row = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()
    # Sessions are in-process; the user row can disappear under a live token
    # if the database is replaced or the volume is reset.
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return {"username": row["username"]}


def _get_board_id(conn, user_id: int) -> int:
    row = conn.execute("SELECT id FROM boards WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board not found")
    return row["id"]


def _get_owned_column(conn, column_id: int, board_id: int):
    row = conn.execute(
        "SELECT id FROM columns WHERE id = ? AND board_id = ?", (column_id, board_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    return row


def _get_owned_card(conn, card_id: int, board_id: int):
    row = conn.execute(
        """
        SELECT cards.* FROM cards
        JOIN columns ON columns.id = cards.column_id
        WHERE cards.id = ? AND columns.board_id = ?
        """,
        (card_id, board_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    return row


def _reindex(conn, column_id: int, moved_card_id: int | None = None, position: int | None = None) -> None:
    """Rewrite a column's positions as 0..n-1, placing moved_card_id at position.

    Writing only the moved card's position leaves duplicates, and ORDER BY
    position then falls back to insertion order, losing the new ordering.
    """
    ids = [
        row["id"]
        for row in conn.execute(
            "SELECT id FROM cards WHERE column_id = ? AND id IS NOT ? ORDER BY position, id",
            (column_id, moved_card_id),
        )
    ]
    if moved_card_id is not None:
        index = len(ids) if position is None else max(0, min(position, len(ids)))
        ids.insert(index, moved_card_id)
    for pos, card_id in enumerate(ids):
        conn.execute("UPDATE cards SET position = ? WHERE id = ?", (pos, card_id))


def _ticket_id_taken(conn, board_id: int, ticket_id: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM cards
        JOIN columns ON columns.id = cards.column_id
        WHERE columns.board_id = ? AND cards.ticket_id = ?
        """,
        (board_id, ticket_id),
    ).fetchone()
    return row is not None


def _next_position(conn, column_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(position) + 1, 0) AS pos FROM cards WHERE column_id = ?", (column_id,)
    ).fetchone()
    return row["pos"]


def _load_board(conn, board_id: int):
    board = conn.execute("SELECT id, name FROM boards WHERE id = ?", (board_id,)).fetchone()
    columns = conn.execute(
        "SELECT id, column_key, title, position FROM columns WHERE board_id = ? ORDER BY position",
        (board_id,),
    ).fetchall()
    cards = conn.execute(
        """
        SELECT cards.*, columns.column_key AS column_key FROM cards
        JOIN columns ON columns.id = cards.column_id
        WHERE columns.board_id = ?
        ORDER BY cards.position, cards.id
        """,
        (board_id,),
    ).fetchall()
    return board, columns, cards


@app.get("/api/board")
def get_board(user_id: int = Depends(require_user)):
    conn = get_connection()
    try:
        board_id = _get_board_id(conn, user_id)
        board, columns, cards = _load_board(conn, board_id)
    finally:
        conn.close()

    return {
        "id": board["id"],
        "name": board["name"],
        "columns": [
            {"id": c["id"], "key": c["column_key"], "title": c["title"], "position": c["position"]}
            for c in columns
        ],
        "cards": [
            {k: c[k] for k in c.keys() if k != "column_key"} for c in cards
        ],
    }


class ColumnUpdate(BaseModel):
    title: str


@app.patch("/api/columns/{column_id}")
def update_column(column_id: int, payload: ColumnUpdate, user_id: int = Depends(require_user)):
    conn = get_connection()
    try:
        board_id = _get_board_id(conn, user_id)
        _get_owned_column(conn, column_id, board_id)
        conn.execute("UPDATE columns SET title = ? WHERE id = ?", (payload.title, column_id))
        conn.commit()
        updated = conn.execute(
            "SELECT id, column_key, title, position FROM columns WHERE id = ?", (column_id,)
        ).fetchone()
    finally:
        conn.close()
    return {"id": updated["id"], "key": updated["column_key"], "title": updated["title"], "position": updated["position"]}


class CardCreate(BaseModel):
    column_id: int
    ticket_id: str
    title: str
    category: str
    priority: str | None = None
    assignee: str
    due_date: str
    progress: int | None = None


@app.post("/api/cards", status_code=status.HTTP_201_CREATED)
def create_card(payload: CardCreate, user_id: int = Depends(require_user)):
    conn = get_connection()
    try:
        board_id = _get_board_id(conn, user_id)
        _get_owned_column(conn, payload.column_id, board_id)
        if _ticket_id_taken(conn, board_id, payload.ticket_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ticket {payload.ticket_id} already exists on this board",
            )
        position = _next_position(conn, payload.column_id)
        cur = conn.execute(
            """
            INSERT INTO cards (column_id, ticket_id, title, category, priority, assignee, due_date, progress, position)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.column_id,
                payload.ticket_id,
                payload.title,
                payload.category,
                payload.priority,
                payload.assignee,
                payload.due_date,
                payload.progress,
                position,
            ),
        )
        conn.commit()
        card = conn.execute("SELECT * FROM cards WHERE id = ?", (cur.lastrowid,)).fetchone()
    finally:
        conn.close()
    return dict(card)


class CardUpdate(BaseModel):
    column_id: int | None = None
    ticket_id: str | None = None
    title: str | None = None
    category: str | None = None
    priority: str | None = None
    assignee: str | None = None
    due_date: str | None = None
    progress: int | None = None
    position: int | None = None


@app.patch("/api/cards/{card_id}")
def update_card(card_id: int, payload: CardUpdate, user_id: int = Depends(require_user)):
    conn = get_connection()
    try:
        board_id = _get_board_id(conn, user_id)
        card = _get_owned_card(conn, card_id, board_id)

        updates = payload.model_dump(exclude_unset=True)
        source_column = card["column_id"]
        target_column = updates.get("column_id", source_column)
        if "column_id" in updates:
            _get_owned_column(conn, target_column, board_id)

        moved = "column_id" in updates or "position" in updates
        position = updates.pop("position", None)

        if updates:
            set_clause = ", ".join(f"{key} = ?" for key in updates)
            conn.execute(f"UPDATE cards SET {set_clause} WHERE id = ?", (*updates.values(), card_id))

        if moved:
            _reindex(conn, target_column, card_id, position)
            if target_column != source_column:
                _reindex(conn, source_column)
        conn.commit()

        updated = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    finally:
        conn.close()
    return dict(updated)


@app.delete("/api/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(card_id: int, user_id: int = Depends(require_user)):
    conn = get_connection()
    try:
        board_id = _get_board_id(conn, user_id)
        _get_owned_card(conn, card_id, board_id)
        conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        conn.commit()
    finally:
        conn.close()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _execute_action(conn, board_id: int, action: dict) -> bool:
    """Apply one model-proposed action. Returns False if it did not apply."""
    action_type = action.get("type")

    if action_type == "create_card":
        column = conn.execute(
            "SELECT id FROM columns WHERE board_id = ? AND column_key = ?",
            (board_id, action.get("column")),
        ).fetchone()
        if (
            column is None
            or not action.get("ticket_id")
            or not action.get("title")
            or not action.get("assignee")
            or not action.get("due_date")
            or _ticket_id_taken(conn, board_id, action["ticket_id"])
        ):
            return False
        position = _next_position(conn, column["id"])
        conn.execute(
            """
            INSERT INTO cards (column_id, ticket_id, title, category, priority, assignee, due_date, progress, position)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                column["id"],
                action["ticket_id"],
                action["title"],
                action.get("category") or "Planning",
                action.get("priority"),
                action["assignee"],
                action["due_date"],
                None,
                position,
            ),
        )

    elif action_type == "edit_card":
        card = conn.execute(
            """
            SELECT cards.id FROM cards
            JOIN columns ON columns.id = cards.column_id
            WHERE columns.board_id = ? AND cards.ticket_id = ?
            ORDER BY cards.id
            """,
            (board_id, action.get("ticket_id")),
        ).fetchone()
        fields = {
            k: v for k, v in action.items()
            if k in {"title", "category", "priority", "assignee", "due_date"}
        }
        if card is None or not fields:
            return False
        set_clause = ", ".join(f"{key} = ?" for key in fields)
        conn.execute(f"UPDATE cards SET {set_clause} WHERE id = ?", (*fields.values(), card["id"]))

    elif action_type == "move_card":
        card = conn.execute(
            """
            SELECT cards.id FROM cards
            JOIN columns ON columns.id = cards.column_id
            WHERE columns.board_id = ? AND cards.ticket_id = ?
            ORDER BY cards.id
            """,
            (board_id, action.get("ticket_id")),
        ).fetchone()
        column = conn.execute(
            "SELECT id FROM columns WHERE board_id = ? AND column_key = ?",
            (board_id, action.get("column")),
        ).fetchone()
        if card is None or column is None:
            return False
        position = _next_position(conn, column["id"])
        conn.execute(
            "UPDATE cards SET column_id = ?, position = ? WHERE id = ?",
            (column["id"], position, card["id"]),
        )

    elif action_type == "rename_column":
        column = conn.execute(
            "SELECT id FROM columns WHERE board_id = ? AND column_key = ?",
            (board_id, action.get("column")),
        ).fetchone()
        title = action.get("title")
        if column is None or not title:
            return False
        conn.execute("UPDATE columns SET title = ? WHERE id = ?", (title, column["id"]))

    else:
        return False

    return True


class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat")
async def chat(payload: ChatRequest, user_id: int = Depends(require_user)):
    # The model call takes seconds, so read the board, release the connection,
    # then reopen to apply whatever comes back.
    conn = get_connection()
    try:
        board_id = _get_board_id(conn, user_id)
        board, columns, cards = _load_board(conn, board_id)
        board_name = board["name"]
        columns_data = [{"key": c["column_key"], "title": c["title"]} for c in columns]
        cards_data = [
            {
                "ticket_id": c["ticket_id"],
                "title": c["title"],
                "category": c["category"],
                "priority": c["priority"],
                "assignee": c["assignee"],
                "due_date": c["due_date"],
                "column_key": c["column_key"],
            }
            for c in cards
        ]
    finally:
        conn.close()

    result = await get_chat_response(payload.message, board_name, columns_data, cards_data)

    conn = get_connection()
    try:
        skipped = 0
        for action in result["actions"]:
            try:
                applied = _execute_action(conn, board_id, action)
            except Exception:
                logger.exception("chat action raised: %s", action)
                applied = False
            if not applied:
                logger.warning("chat action not applied: %s", action)
                skipped += 1
        conn.commit()
    finally:
        conn.close()

    reply = result["reply"]
    if skipped:
        # The model's reply already claimed the change; say what really happened.
        total = len(result["actions"])
        reply = f"{reply} ({skipped} of {total} changes could not be applied.)"

    return {"reply": reply}


# Static export of the frontend, mounted last so /api/* routes take precedence.
# Absent until `npm run build` has run, so the backend still starts on its own.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "out"

if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
