"use client";

import { useMemo, useState } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  closestCorners,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { arrayMove } from "@dnd-kit/sortable";
import type { CardData, ColumnDef, ColumnId } from "@/lib/types";
import { Column } from "./Column";
import { CardItem } from "./CardItem";

interface BoardProps {
  columns: ColumnDef[];
  cards: CardData[];
  searchQuery: string;
  onCardsChange: (cards: CardData[]) => void;
  onDeleteCard: (id: string) => void;
  onRenameColumn: (id: ColumnId, title: string) => void;
  onAddCard: (card: CardData) => void;
  onEditCard: (id: string, updates: Partial<CardData>) => void;
  onMoveCard: (id: string, columnId: ColumnId, position: number) => void;
}

export function Board({
  columns,
  cards,
  searchQuery,
  onCardsChange,
  onDeleteCard,
  onRenameColumn,
  onAddCard,
  onEditCard,
  onMoveCard,
}: BoardProps) {
  const [activeCard, setActiveCard] = useState<CardData | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  const query = searchQuery.trim().toLowerCase();
  const visibleCards = useMemo(() => {
    if (!query) return cards;
    return cards.filter(
      (c) =>
        c.title.toLowerCase().includes(query) ||
        c.ticketId.toLowerCase().includes(query)
    );
  }, [cards, query]);

  function findColumnOf(id: string): ColumnId | undefined {
    return cards.find((c) => c.id === id)?.columnId;
  }

  function handleDragStart(event: DragStartEvent) {
    const card = cards.find((c) => c.id === event.active.id);
    setActiveCard(card ?? null);
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveCard(null);
    const { active, over } = event;
    if (!over) return;

    const activeId = String(active.id);
    const overId = String(over.id);
    if (activeId === overId) return;

    const activeColumn = findColumnOf(activeId);
    const overColumn = columns.some((c) => c.id === overId)
      ? (overId as ColumnId)
      : findColumnOf(overId);

    if (!activeColumn || !overColumn) return;

    if (activeColumn === overColumn) {
      const activeIndex = cards.findIndex((c) => c.id === activeId);
      const overIndex = cards.findIndex((c) => c.id === overId);
      if (overIndex === -1 || activeIndex === overIndex) return;
      const reordered = arrayMove(cards, activeIndex, overIndex);
      onCardsChange(reordered);
      const position = reordered
        .filter((c) => c.columnId === activeColumn)
        .findIndex((c) => c.id === activeId);
      onMoveCard(activeId, activeColumn, position);
    } else {
      const updated = cards.map((c) =>
        c.id === activeId ? { ...c, columnId: overColumn } : c
      );
      const newActiveIndex = updated.findIndex((c) => c.id === activeId);
      const overIndex = updated.findIndex((c) => c.id === overId);
      const finalCards =
        overIndex !== -1
          ? arrayMove(updated, newActiveIndex, overIndex)
          : updated;
      onCardsChange(finalCards);
      const position = finalCards
        .filter((c) => c.columnId === overColumn)
        .findIndex((c) => c.id === activeId);
      onMoveCard(activeId, overColumn, position);
    }
  }

  return (
    <DndContext
      id="netops-board"
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="grid grid-cols-1 gap-4 p-6 md:grid-cols-2 xl:grid-cols-4">
        {columns.map((column) => (
          <Column
            key={column.id}
            column={column}
            cards={visibleCards.filter((c) => c.columnId === column.id)}
            allCards={cards}
            onDeleteCard={onDeleteCard}
            onRenameColumn={onRenameColumn}
            onAddCard={onAddCard}
            onEditCard={onEditCard}
          />
        ))}
      </div>
      <DragOverlay>
        {activeCard ? (
          <CardItem card={activeCard} onDelete={() => {}} overlay />
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
