import type { APIRequestContext } from "@playwright/test";

// The board is backed by a persistent database, so tests set up and tear down
// their own cards instead of mutating the seed data.

export interface BoardColumn {
  id: number;
  key: string;
  title: string;
}

export interface BoardCard {
  id: number;
  column_id: number;
  ticket_id: string;
  title: string;
}

export async function signIn(request: APIRequestContext): Promise<string> {
  const res = await request.post("/api/login", {
    data: { username: "user", password: "password" },
  });
  return (await res.json()).token;
}

const auth = (token: string) => ({ Authorization: `Bearer ${token}` });

export async function getBoard(
  request: APIRequestContext,
  token: string
): Promise<{ columns: BoardColumn[]; cards: BoardCard[] }> {
  const res = await request.get("/api/board", { headers: auth(token) });
  return res.json();
}

export async function columnByKey(
  request: APIRequestContext,
  token: string,
  key: string
): Promise<BoardColumn> {
  const board = await getBoard(request, token);
  const column = board.columns.find((c) => c.key === key);
  if (!column) throw new Error(`No column with key ${key}`);
  return column;
}

let counter = 0;

export async function createCard(
  request: APIRequestContext,
  token: string,
  columnKey: string,
  overrides: Partial<BoardCard> & Record<string, unknown> = {}
): Promise<BoardCard> {
  const column = await columnByKey(request, token, columnKey);
  const res = await request.post("/api/cards", {
    headers: auth(token),
    data: {
      column_id: column.id,
      ticket_id: `E2E-${Date.now()}-${counter++}`,
      title: "E2E fixture card",
      category: "Planning",
      priority: null,
      assignee: "ZZ",
      due_date: "2030-01-01",
      progress: null,
      ...overrides,
    },
  });
  return res.json();
}

export async function deleteCard(
  request: APIRequestContext,
  token: string,
  cardId: number
): Promise<void> {
  await request.delete(`/api/cards/${cardId}`, { headers: auth(token) });
}

export async function moveCard(
  request: APIRequestContext,
  token: string,
  cardId: number,
  columnId: number,
  position: number
): Promise<void> {
  await request.patch(`/api/cards/${cardId}`, {
    headers: auth(token),
    data: { column_id: columnId, position },
  });
}

export async function renameColumn(
  request: APIRequestContext,
  token: string,
  columnId: number,
  title: string
): Promise<void> {
  await request.patch(`/api/columns/${columnId}`, {
    headers: auth(token),
    data: { title },
  });
}
