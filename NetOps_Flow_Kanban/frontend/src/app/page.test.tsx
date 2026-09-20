import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Home from "./page";
import { ApiError, deleteCard, fetchBoard, fetchMe } from "@/lib/api";
import { getStoredToken } from "@/lib/session";

vi.mock("@/lib/api", () => ({
  fetchMe: vi.fn(),
  fetchBoard: vi.fn(),
  createCard: vi.fn(),
  deleteCard: vi.fn(),
  updateCard: vi.fn(),
  renameColumn: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(public status: number) {
      super(`Request failed: ${status}`);
    }
  },
}));

vi.mock("@/lib/session", () => ({
  getStoredToken: vi.fn(),
  storeToken: vi.fn(),
  clearToken: vi.fn(),
}));

describe("Home session check", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("falls back to sign-in when the backend is unreachable", async () => {
    vi.mocked(getStoredToken).mockReturnValue("stale-token");
    // fetch rejects (not resolves) when the backend is down
    vi.mocked(fetchMe).mockRejectedValue(new TypeError("Failed to fetch"));

    render(<Home />);

    expect(
      await screen.findByRole("button", { name: "Sign in" })
    ).toBeInTheDocument();
  });

  it("shows sign-in when there is no stored token", async () => {
    vi.mocked(getStoredToken).mockReturnValue(null);

    render(<Home />);

    expect(
      await screen.findByRole("button", { name: "Sign in" })
    ).toBeInTheDocument();
  });
});

const BOARD = {
  id: 1,
  name: "Board",
  columns: [
    { id: 1, key: "backlog", title: "Backlog", position: 0 },
    { id: 2, key: "in-progress", title: "In Progress", position: 1 },
    { id: 3, key: "cab", title: "Change Review (CAB)", position: 2 },
    { id: 4, key: "deployed", title: "Deployed", position: 3 },
  ],
  cards: [
    {
      id: 10,
      column_id: 1,
      ticket_id: "CHG-1",
      title: "A card",
      category: "Network",
      priority: null,
      assignee: "AA",
      due_date: "2030-01-01",
      progress: null,
      position: 0,
    },
  ],
};

describe("failed mutations", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getStoredToken).mockReturnValue("token");
    vi.mocked(fetchMe).mockResolvedValue({ username: "user" });
    vi.mocked(fetchBoard).mockResolvedValue(BOARD);
  });

  it("resyncs with the server when a card mutation fails", async () => {
    vi.mocked(deleteCard).mockRejectedValue(new ApiError(500));

    render(<Home />);
    const card = await screen.findByText("A card");
    expect(card).toBeInTheDocument();
    expect(fetchBoard).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByLabelText("Delete CHG-1"));

    // The optimistic UI must not be trusted after a failure.
    await waitFor(() => expect(fetchBoard).toHaveBeenCalledTimes(2));
  });
});
