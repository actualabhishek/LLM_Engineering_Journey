"use client";

import { useState, type FormEvent } from "react";
import type { CardData, Category, Priority } from "@/lib/types";

interface EditCardModalProps {
  card: CardData;
  onClose: () => void;
  onSubmit: (updates: Partial<CardData>) => void;
}

const CATEGORIES: Category[] = [
  "Network",
  "Security",
  "Incident",
  "Access",
  "Planning",
];

export function EditCardModal({ card, onClose, onSubmit }: EditCardModalProps) {
  const [title, setTitle] = useState(card.title);
  const [category, setCategory] = useState<Category>(card.category);
  const [priority, setPriority] = useState<Priority | "">(card.priority ?? "");
  const [assignee, setAssignee] = useState(card.assignee);
  const [dueDate, setDueDate] = useState(card.dueDate);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim() || !assignee.trim() || !dueDate) return;

    onSubmit({
      title: title.trim(),
      category,
      priority: priority || undefined,
      assignee: assignee.trim().slice(0, 2).toUpperCase(),
      dueDate,
    });
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
          Edit card
        </h3>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <label className="text-xs font-medium text-muted">
            Title
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              className="mt-1 w-full rounded-md border border-line bg-field px-2 py-1.5 text-sm text-ink"
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
              Save
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
