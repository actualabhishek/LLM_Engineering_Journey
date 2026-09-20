import type { BackendCard, BackendColumn } from "./api";
import type { CardData, Category, ColumnDef, ColumnId, Priority } from "./types";

export function toColumnDefs(columns: BackendColumn[]): ColumnDef[] {
  return columns
    .slice()
    .sort((a, b) => a.position - b.position)
    .map((c) => ({ id: c.key as ColumnId, title: c.title }));
}

export function toCardData(cards: BackendCard[], columns: BackendColumn[]): CardData[] {
  const keyById = new Map(columns.map((c) => [c.id, c.key as ColumnId]));
  return cards
    .slice()
    .sort((a, b) => a.position - b.position)
    .map((c) => ({
      id: String(c.id),
      ticketId: c.ticket_id,
      title: c.title,
      category: c.category as Category,
      priority: (c.priority ?? undefined) as Priority | undefined,
      assignee: c.assignee,
      dueDate: c.due_date,
      progress: c.progress ?? undefined,
      columnId: keyById.get(c.column_id) as ColumnId,
    }));
}

export function columnIdMap(columns: BackendColumn[]): Record<string, number> {
  return Object.fromEntries(columns.map((c) => [c.key, c.id]));
}
