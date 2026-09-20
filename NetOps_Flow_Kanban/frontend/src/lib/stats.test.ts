import { describe, expect, it } from "vitest";
import { computeStats } from "./stats";
import type { CardData } from "./types";

const NOW = new Date("2026-09-18T12:00:00");

function card(overrides: Partial<CardData>): CardData {
  return {
    id: "card-x",
    ticketId: "TASK-1",
    title: "Sample",
    category: "Planning",
    assignee: "AS",
    dueDate: "2026-09-25",
    columnId: "backlog",
    ...overrides,
  };
}

describe("computeStats", () => {
  it("counts open change requests as CHG tickets not yet deployed", () => {
    const cards = [
      card({ ticketId: "CHG-1", columnId: "backlog" }),
      card({ ticketId: "CHG-2", columnId: "cab" }),
      card({ ticketId: "CHG-3", columnId: "deployed" }),
      card({ ticketId: "TASK-1", columnId: "backlog" }),
    ];
    expect(computeStats(cards, NOW).openChangeRequests).toBe(2);
  });

  it("counts active P1/P2 incidents not yet deployed", () => {
    const cards = [
      card({ ticketId: "INC-1", priority: "P1", columnId: "in-progress" }),
      card({ ticketId: "INC-2", priority: "P2", columnId: "backlog" }),
      card({ ticketId: "INC-3", columnId: "backlog" }),
      card({ ticketId: "INC-4", priority: "P1", columnId: "deployed" }),
    ];
    expect(computeStats(cards, NOW).activeIncidents).toBe(2);
  });

  it("flags cards due today or overdue as SLA at risk, excluding cab and deployed", () => {
    const cards = [
      card({ ticketId: "TASK-1", dueDate: "2026-09-18", columnId: "backlog" }),
      card({ ticketId: "TASK-2", dueDate: "2026-09-15", columnId: "in-progress" }),
      card({ ticketId: "TASK-3", dueDate: "2026-09-30", columnId: "backlog" }),
      card({ ticketId: "CHG-1", dueDate: "2026-09-18", columnId: "cab" }),
      card({ ticketId: "CHG-2", dueDate: "2026-09-18", columnId: "deployed" }),
    ];
    expect(computeStats(cards, NOW).slaAtRisk).toBe(2);
  });

  it("counts deployments that fall within the current week", () => {
    const cards = [
      card({ ticketId: "CHG-1", dueDate: "2026-09-16", columnId: "deployed" }),
      card({ ticketId: "CHG-2", dueDate: "2026-09-01", columnId: "deployed" }),
      card({ ticketId: "CHG-3", dueDate: "2026-09-17", columnId: "backlog" }),
    ];
    expect(computeStats(cards, NOW).deploymentsThisWeek).toBe(1);
  });

  it("returns zeros for an empty board", () => {
    expect(computeStats([], NOW)).toEqual({
      openChangeRequests: 0,
      activeIncidents: 0,
      slaAtRisk: 0,
      deploymentsThisWeek: 0,
    });
  });
});
