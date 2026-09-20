import type { CardData, TicketPrefix } from "./types";

export function nextTicketId(cards: CardData[], prefix: TicketPrefix): string {
  const numbers = cards
    .filter((c) => c.ticketId.startsWith(`${prefix}-`))
    .map((c) => parseInt(c.ticketId.split("-")[1], 10))
    .filter((n) => !Number.isNaN(n));
  const max = numbers.length > 0 ? Math.max(...numbers) : prefix === "CHG" ? 1000 : prefix === "INC" ? 2000 : 1000;
  return `${prefix}-${max + 1}`;
}
