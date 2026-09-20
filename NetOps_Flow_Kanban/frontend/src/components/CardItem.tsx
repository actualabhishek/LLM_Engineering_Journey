"use client";

import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { CardData } from "@/lib/types";
import { CategoryBadge, PriorityBadge } from "./Badge";
import { Avatar } from "./Avatar";
import { formatDate, formatMaintenanceWindow } from "@/lib/dates";

interface CardItemProps {
  card: CardData;
  onDelete: (id: string) => void;
  onEdit?: (card: CardData) => void;
  overlay?: boolean;
}

export function CardItem({ card, onDelete, onEdit, overlay }: CardItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: card.id, disabled: overlay });

  const style = overlay
    ? undefined
    : {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.4 : 1,
      };

  return (
    <div
      ref={overlay ? undefined : setNodeRef}
      style={style}
      {...(overlay ? {} : attributes)}
      {...(overlay ? {} : listeners)}
      data-testid="card"
      data-ticket-id={card.ticketId}
      className={`group cursor-grab rounded-lg border border-line bg-raised p-3 active:cursor-grabbing ${
        overlay ? "ring-2 ring-accent-blue/40" : "hover:border-accent-blue/40"
      }`}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <span className="text-xs font-semibold text-muted">
          {card.ticketId}
        </span>
        <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          {onEdit && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onEdit(card);
              }}
              onPointerDown={(e) => e.stopPropagation()}
              className="text-muted hover:text-accent-blue"
              aria-label={`Edit ${card.ticketId}`}
            >
              &#9998;
            </button>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete(card.id);
            }}
            onPointerDown={(e) => e.stopPropagation()}
            className="text-muted hover:text-danger-red"
            aria-label={`Delete ${card.ticketId}`}
          >
            &times;
          </button>
        </div>
      </div>

      <p className="mb-2 text-sm font-medium leading-snug text-ink">
        {card.title}
      </p>

      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        <CategoryBadge category={card.category} />
        {card.priority && <PriorityBadge priority={card.priority} />}
        {card.columnId === "cab" && (
          <span className="inline-flex items-center rounded-full bg-warning-amber/15 px-2 py-0.5 text-[11px] font-medium text-warning-amber">
            Awaiting CAB approval
          </span>
        )}
      </div>

      {card.columnId === "in-progress" && typeof card.progress === "number" && (
        <div className="mb-3">
          <div className="mb-1 flex items-center justify-between text-[11px] text-muted">
            <span>Progress</span>
            <span>{card.progress}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full rounded-full bg-accent-blue"
              style={{ width: `${card.progress}%` }}
            />
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-muted">
          {card.columnId === "cab"
            ? formatMaintenanceWindow(card.dueDate)
            : `Due ${formatDate(card.dueDate)}`}
        </span>
        <Avatar initials={card.assignee} />
      </div>
    </div>
  );
}
