import { colorForInitials } from "@/lib/avatarColor";

export function Avatar({ initials }: { initials: string }) {
  return (
    <div
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white"
      style={{ backgroundColor: colorForInitials(initials) }}
      title={initials}
    >
      {initials.slice(0, 2).toUpperCase()}
    </div>
  );
}
