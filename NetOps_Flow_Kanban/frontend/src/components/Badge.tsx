import type { Category, Priority } from "@/lib/types";

const CATEGORY_STYLES: Record<Category, string> = {
  Network: "bg-accent-blue/15 text-accent-blue",
  Security: "bg-warning-amber/15 text-warning-amber",
  Incident: "bg-danger-red/15 text-danger-red",
  Access: "bg-accent-purple/15 text-accent-purple",
  Planning: "bg-white/8 text-muted",
};

export function CategoryBadge({ category }: { category: Category }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${CATEGORY_STYLES[category]}`}
    >
      {category}
    </span>
  );
}

const PRIORITY_STYLES: Record<Priority, string> = {
  P1: "bg-danger-red text-[#25090b]",
  P2: "bg-warning-amber text-[#231803]",
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${PRIORITY_STYLES[priority]}`}
    >
      {priority}
    </span>
  );
}
