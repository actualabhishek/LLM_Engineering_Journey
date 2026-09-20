// Dev runs the frontend on :3000 and the backend on :8000; the built app is served
// by the backend from a single origin, so requests go to relative paths.
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");

export class ApiError extends Error {
  constructor(public status: number) {
    super(`Request failed: ${status}`);
  }
}

export async function login(username: string, password: string): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/api/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new ApiError(res.status);
  const data = await res.json();
  return data.token as string;
}

export async function fetchMe(token: string): Promise<{ username: string } | null> {
  const res = await fetch(`${API_BASE_URL}/api/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  return res.json();
}

export interface BackendColumn {
  id: number;
  key: string;
  title: string;
  position: number;
}

export interface BackendCard {
  id: number;
  column_id: number;
  ticket_id: string;
  title: string;
  category: string;
  priority: string | null;
  assignee: string;
  due_date: string;
  progress: number | null;
  position: number;
}

export interface BoardResponse {
  id: number;
  name: string;
  columns: BackendColumn[];
  cards: BackendCard[];
}

async function authFetch(token: string, path: string, options: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...options.headers,
    },
  });
  if (!res.ok) throw new ApiError(res.status);
  return res;
}

export async function fetchBoard(token: string): Promise<BoardResponse> {
  const res = await authFetch(token, "/api/board");
  return res.json();
}

export interface CardWritePayload {
  column_id: number;
  ticket_id: string;
  title: string;
  category: string;
  priority?: string | null;
  assignee: string;
  due_date: string;
  progress?: number | null;
}

export async function createCard(token: string, payload: CardWritePayload): Promise<BackendCard> {
  const res = await authFetch(token, "/api/cards", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function updateCard(
  token: string,
  cardId: number,
  payload: Partial<CardWritePayload> & { position?: number }
): Promise<BackendCard> {
  const res = await authFetch(token, `/api/cards/${cardId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function deleteCard(token: string, cardId: number): Promise<void> {
  await authFetch(token, `/api/cards/${cardId}`, { method: "DELETE" });
}

export async function renameColumn(token: string, columnId: number, title: string): Promise<BackendColumn> {
  const res = await authFetch(token, `/api/columns/${columnId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
  return res.json();
}

export async function sendChatMessage(token: string, message: string): Promise<string> {
  const res = await authFetch(token, "/api/chat", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
  const data = await res.json();
  return data.reply as string;
}
