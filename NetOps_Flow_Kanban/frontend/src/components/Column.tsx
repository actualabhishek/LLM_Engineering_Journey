"use client";

import { useState } from "react";
import { useDroppable } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import type { CardData, ColumnDef, ColumnId } from "@/lib/types";
import { CardItem } from "./CardItem";
import { AddCardModal } from "./AddCardModal";
import { EditCardModal } from "./EditCardModal";

interface ColumnProps {
  column: ColumnDef;
  cards: CardData[];
  allCards: CardData[];
  onDeleteCard: (id: string) => void;
  onRenameColumn: (id: ColumnId, title: string) => void;
  onAddCard: (card: CardData) => void;
  onEditCard: (id: string, updates: Partial<CardData>) => void;
}

const HEADER_ACCENT: Record<ColumnId, string> = {
  backlog: "bg-muted",
  "in-progress": "bg-accent-blue",
  cab: "bg-warning-amber",
  deployed: "bg-success-green",
};

export function Column({
  column,
  cards,
  allCards,
  onDeleteCard,
  onRenameColumn,
  onAddCard,
  onEditCard,
}: ColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id: column.id });
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(column.title);
  const [formOpen, setFormOpen] = useState(false);
  const [editingCard, setEditingCard] = useState<CardData | null>(null);

  function commitTitle() {
    setEditing(false);
    const trimmed = draftTitle.trim();
    if (trimmed && trimmed !== column.title) {
      onRenameColumn(column.id, trimmed);
    } else {
      setDraftTitle(column.title);
    }
  }

  return (
    <div
      data-testid="column"
      data-column-id={column.id}
      className="flex flex-col rounded-xl border border-line bg-surface"
    >
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className={`h-2 w-2 shrink-0 rounded-full ${HEADER_ACCENT[column.id]}`}
          />
          {editing ? (
            <input
              autoFocus
              aria-label={`Rename ${column.title} column`}
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
              onBlur={commitTitle}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitTitle();
                if (e.key === "Escape") {
                  setDraftTitle(column.title);
                  setEditing(false);
                }
              }}
              className="w-full rounded border border-accent-blue bg-field px-1 text-sm font-semibold text-ink outline-none"
            />
          ) : (
            <h2
              onClick={() => setEditing(true)}
              className="cursor-text truncate text-sm font-semibold text-ink"
              title="Click to rename"
            >
              {column.title}
            </h2>
          )}
        </div>
        <span className="shrink-0 rounded-full bg-white/5 px-2 py-0.5 text-xs font-medium text-muted">
          {cards.length}
        </span>
      </div>

      <div
        ref={setNodeRef}
        className={`flex min-h-[120px] flex-1 flex-col gap-3 p-3 transition-colors ${
          isOver ? "bg-accent-blue/10" : ""
        }`}
      >
        <SortableContext
          items={cards.map((c) => c.id)}
          strategy={verticalListSortingStrategy}
        >
          {cards.map((card) => (
            <CardItem
              key={card.id}
              card={card}
              onDelete={onDeleteCard}
              onEdit={setEditingCard}
            />
          ))}
        </SortableContext>
      </div>

      <div className="border-t border-line p-2">
        <button
          onClick={() => setFormOpen(true)}
          className="w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-muted hover:bg-white/5 hover:text-accent-blue"
        >
          + Add card
        </button>
      </div>

      {formOpen && (
        <AddCardModal
          columnId={column.id}
          allCards={allCards}
          onClose={() => setFormOpen(false)}
          onSubmit={(card) => {
            onAddCard(card);
            setFormOpen(false);
          }}
        />
      )}

      {editingCard && (
        <EditCardModal
          card={editingCard}
          onClose={() => setEditingCard(null)}
          onSubmit={(updates) => {
            onEditCard(editingCard.id, updates);
            setEditingCard(null);
          }}
        />
      )}
    </div>
  );
}
