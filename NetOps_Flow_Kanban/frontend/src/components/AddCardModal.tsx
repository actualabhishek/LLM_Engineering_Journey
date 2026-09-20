"use client";

import { useState, type FormEvent } from "react";
import type {
  CardData,
  Category,
  ColumnId,
  Priority,
  TicketPrefix,
} from "@/lib/types";
import { nextTicketId } from "@/lib/ticketId";

interface AddCardModalProps {
  columnId: ColumnId;
  allCards: CardData[];
  onClose: () => void;
  onSubmit: (card: CardData) => void;
}

const CATEGORIES: Category[] = [
  "Network",
  "Security",
  "Incident",
  "Access",
  "Planning",
];
const PREFIXES: TicketPrefix[] = ["CHG", "INC", "TASK"];

export function AddCardModal({
  columnId,
  allCards,
  onClose,
  onSubmit,
}: AddCardModalProps) {
  const [prefix, setPrefix] = useState<TicketPrefix>("TASK");
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState<Category>("Network");
  const [priority, setPriority] = useState<Priority | "">("");
  const [assignee, setAssignee] = useState("");
  const [dueDate, setDueDate] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim() || !assignee.trim() || !dueDate) return;

    const card: CardData = {
      id: `card-${Date.now()}-${Math.round(Math.random() * 1000)}`,
      ticketId: nextTicketId(allCards, prefix),
      title: title.trim(),
      category,
      priority: priority || undefined,
      assignee: assignee.trim().slice(0, 2).toUpperCase(),
      dueDate,
      progress: columnId === "in-progress" ? 0 : undefined,
      columnId,
    };
    onSubmit(card);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-xl border border-line bg-surface p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-4 text-sm font-semibold text-ink">
          Add card
        </h3>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <label className="text-xs font-medium text-muted">
            Ticket prefix
            <select
              value={prefix}
              onChange={(e) => setPrefix(e.target.value as TicketPrefix)}
              className="mt-1 w-full rounded-md border border-line bg-field px-2 py-1.5 text-sm text-ink"
            >
              {PREFIXES.map((p) => (
                <option key={p} value={p}>
                  {p}-
                </option>
              ))}
            </select>
          </label>

          <label className="text-xs font-medium text-muted">
            Title
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              className="mt-1 w-full rounded-md border border-line bg-field px-2 py-1.5 text-sm text-ink"
              placeholder="e.g. Patch edge firewalls"
            />
          </label>

          <div className="flex gap-2">
            <label className="flex-1 text-xs font-medium text-muted">
              Category
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as Category)}
                className="mt-1 w-full rounded-md border border-line bg-field px-2 py-1.5 text-sm text-ink"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex-1 text-xs font-medium text-muted">
              Priority
              <select
                value={priority}
                onChange={(e) =>
                  setPriority(e.target.value as Priority | "")
                }
                className="mt-1 w-full rounded-md border border-line bg-field px-2 py-1.5 text-sm text-ink"
              >
                <option value="">None</option>
                <option value="P1">P1</option>
                <option value="P2">P2</option>
              </select>
            </label>
          </div>

          <div className="flex gap-2">
            <label className="flex-1 text-xs font-medium text-muted">
              Assignee
              <input
                value={assignee}
                onChange={(e) => setAssignee(e.target.value)}
                required
                maxLength={2}
                placeholder="AS"
                className="mt-1 w-full rounded-md border border-line bg-field px-2 py-1.5 text-sm uppercase text-ink"
              />
            </label>
            <label className="flex-1 text-xs font-medium text-muted">
              Due date
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                required
                className="mt-1 w-full rounded-md border border-line bg-field px-2 py-1.5 text-sm text-ink"
              />
            </label>
          </div>

          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md px-3 py-1.5 text-sm font-medium text-muted hover:bg-white/5"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="rounded-md bg-accent-solid px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-solid-hover"
            >
              Add card
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
