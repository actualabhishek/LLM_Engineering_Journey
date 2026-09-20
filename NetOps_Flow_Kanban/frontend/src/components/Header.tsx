"use client";

interface HeaderProps {
  searchQuery: string;
  onSearchChange: (value: string) => void;
}

export function Header({ searchQuery, onSearchChange }: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-line bg-surface px-6 py-4">
      <div>
        <h1 className="text-lg font-semibold text-ink">Board</h1>
        <p className="text-xs text-muted">Network Operations</p>
      </div>
      <div className="w-72">
        <input
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search by title or ticket ID"
          aria-label="Search cards"
          className="w-full rounded-lg border border-line bg-field px-3 py-2 text-sm text-ink outline-none focus:border-accent-blue focus:bg-surface"
        />
      </div>
    </header>
  );
}
