import type { CardData } from "./types";
import { daysBetween, daysFromNow, startOfWeek, endOfWeek } from "./dates";

export interface StatsSummary {
  openChangeRequests: number;
  activeIncidents: number;
  slaAtRisk: number;
  deploymentsThisWeek: number;
}

export function computeStats(cards: CardData[], now: Date = new Date()): StatsSummary {
  const todayIso = daysFromNow(0, now);

  const openChangeRequests = cards.filter(
    (c) => c.ticketId.startsWith("CHG-") && c.columnId !== "deployed"
  ).length;

  const activeIncidents = cards.filter(
    (c) =>
      c.ticketId.startsWith("INC-") &&
      c.columnId !== "deployed" &&
      (c.priority === "P1" || c.priority === "P2")
  ).length;

  const slaAtRisk = cards.filter((c) => {
    if (c.columnId === "deployed" || c.columnId === "cab") return false;
    return daysBetween(todayIso, c.dueDate) <= 1;
  }).length;

  const weekStart = startOfWeek(now);
  const weekEnd = endOfWeek(now);
  const deploymentsThisWeek = cards.filter((c) => {
    if (c.columnId !== "deployed") return false;
    const due = new Date(`${c.dueDate}T00:00:00`);
    return due >= weekStart && due <= weekEnd;
  }).length;

  return { openChangeRequests, activeIncidents, slaAtRisk, deploymentsThisWeek };
}
