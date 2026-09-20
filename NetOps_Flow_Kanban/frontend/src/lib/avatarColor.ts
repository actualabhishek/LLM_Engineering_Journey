const PALETTE = [
  "#4a86bb",
  "#45936a",
  "#c2952f",
  "#c25a5a",
  "#8a72b5",
  "#2f9189",
  "#b56a3f",
  "#5a7aa6",
];

export function colorForInitials(initials: string): string {
  let hash = 0;
  for (let i = 0; i < initials.length; i++) {
    hash = (hash * 31 + initials.charCodeAt(i)) >>> 0;
  }
  return PALETTE[hash % PALETTE.length];
}
