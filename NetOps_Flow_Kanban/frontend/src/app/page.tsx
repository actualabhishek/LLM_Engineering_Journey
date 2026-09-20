"use client";

import { useEffect, useMemo, useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";
import { StatsStrip } from "@/components/StatsStrip";
import { Board } from "@/components/Board";
import { ChatSidebar } from "@/components/ChatSidebar";
import { LoginForm } from "@/components/LoginForm";
import {
  ApiError,
  createCard,
  deleteCard,
  fetchBoard,
  fetchMe,
  renameColumn,
  updateCard,
} from "@/lib/api";
import { columnIdMap, toCardData, toColumnDefs } from "@/lib/board";
import { clearToken, getStoredToken, storeToken } from "@/lib/session";
import { computeStats } from "@/lib/stats";
import type { CardData, ColumnDef, ColumnId } from "@/lib/types";

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  // Starts true so the first render matches the prerendered HTML; the stored
  // token is only read in the effect, which never runs at build time.
  const [checkingSession, setCheckingSession] = useState(true);

  useEffect(() => {
    const stored = getStoredToken();
    const check = stored ? fetchMe(stored) : Promise.resolve(null);
    check
      .then((me) => {
        if (stored && me) {
          setToken(stored);
        } else {
          clearToken();
        }
      })
      // fetch rejects when the backend is unreachable; without this the
      // check never finishes and the app renders nothing at all.
      .catch(() => clearToken())
      .finally(() => setCheckingSession(false));
  }, []);

  const [columns, setColumns] = useState<ColumnDef[]>([]);
  const [cards, setCards] = useState<CardData[]>([]);
  const [columnDbIds, setColumnDbIds] = useState<Record<string, number>>({});
  const [searchQuery, setSearchQuery] = useState("");

  function signOut() {
    clearToken();
    setToken(null);
    setColumns([]);
    setCards([]);
  }

  function loadBoard(authToken: string) {
    fetchBoard(authToken).then((board) => {
      setColumns(toColumnDefs(board.columns));
      setCards(toCardData(board.cards, board.columns));
      setColumnDbIds(columnIdMap(board.columns));
    }, (err) => {
      if (err instanceof ApiError && err.status === 401) signOut();
    });
  }

  useEffect(() => {
    if (!token) return;
    loadBoard(token);
  }, [token]);

  const stats = useMemo(() => computeStats(cards), [cards]);

  function withAuth<T extends unknown[]>(
    fn: (token: string, ...args: T) => Promise<unknown>
  ) {
    return async (...args: T) => {
      if (!token) return;
      try {
        await fn(token, ...args);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          signOut();
        } else {
          console.error(err);
          // Drag-and-drop updates the board before the request completes, so
          // resync with the server rather than leaving a change that failed.
          loadBoard(token);
        }
      }
    };
  }

  const handleRenameColumn = withAuth(async (authToken, id: ColumnId, title: string) => {
    await renameColumn(authToken, columnDbIds[id], title);
    setColumns((prev) => prev.map((c) => (c.id === id ? { ...c, title } : c)));
  });

  const handleAddCard = withAuth(async (authToken, card: CardData) => {
    const created = await createCard(authToken, {
      column_id: columnDbIds[card.columnId],
      ticket_id: card.ticketId,
      title: card.title,
      category: card.category,
      priority: card.priority ?? null,
      assignee: card.assignee,
      due_date: card.dueDate,
      progress: card.progress ?? null,
    });
    setCards((prev) => [...prev, { ...card, id: String(created.id) }]);
  });

  const handleDeleteCard = withAuth(async (authToken, id: string) => {
    await deleteCard(authToken, Number(id));
    setCards((prev) => prev.filter((c) => c.id !== id));
  });

  const handleEditCard = withAuth(
    async (authToken, id: string, updates: Partial<CardData>) => {
      await updateCard(authToken, Number(id), {
        title: updates.title,
        category: updates.category,
        priority: updates.priority ?? null,
        assignee: updates.assignee,
        due_date: updates.dueDate,
      });
      setCards((prev) =>
        prev.map((c) => (c.id === id ? { ...c, ...updates } : c))
      );
    }
  );

  const handleMoveCard = withAuth(
    async (authToken, id: string, columnId: ColumnId, position: number) => {
      await updateCard(authToken, Number(id), {
        column_id: columnDbIds[columnId],
        position,
      });
    }
  );

  function handleCardsChange(updated: CardData[]) {
    setCards(updated);
  }

  if (checkingSession) {
    return null;
  }

  if (!token) {
    return (
      <LoginForm
        onSuccess={(newToken) => {
          storeToken(newToken);
          setToken(newToken);
        }}
      />
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Header searchQuery={searchQuery} onSearchChange={setSearchQuery} />
        <main className="flex-1 overflow-y-auto">
          <StatsStrip stats={stats} />
          <Board
            columns={columns}
            cards={cards}
            searchQuery={searchQuery}
            onCardsChange={handleCardsChange}
            onDeleteCard={handleDeleteCard}
            onRenameColumn={handleRenameColumn}
            onAddCard={handleAddCard}
            onEditCard={handleEditCard}
            onMoveCard={handleMoveCard}
          />
        </main>
      </div>
      <ChatSidebar token={token} onBoardChanged={() => loadBoard(token)} />
    </div>
  );
}
