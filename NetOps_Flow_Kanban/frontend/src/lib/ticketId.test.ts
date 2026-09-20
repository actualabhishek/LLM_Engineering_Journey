import { describe, expect, it } from "vitest";
import { nextTicketId } from "./ticketId";
import type { CardData } from "./types";

function card(ticketId: string): CardData {
  return {
    id: ticketId,
    ticketId,
    title: "Sample",
    category: "Planning",
    assignee: "AS",
    dueDate: "2026-09-25",
    columnId: "backlog",
  };
}

describe("nextTicketId", () => {
  it("increments from the highest existing number for a prefix", () => {
    const cards = [card("CHG-1050"), card("CHG-1090"), card("TASK-1005")];
    expect(nextTicketId(cards, "CHG")).toBe("CHG-1091");
  });

  it("starts from a sensible base when no tickets of that prefix exist", () => {
    expect(nextTicketId([], "INC")).toBe("INC-2001");
    expect(nextTicketId([], "TASK")).toBe("TASK-1001");
    expect(nextTicketId([], "CHG")).toBe("CHG-1001");
  });

  it("ignores tickets from other prefixes", () => {
    const cards = [card("CHG-1090"), card("INC-2041")];
    expect(nextTicketId(cards, "INC")).toBe("INC-2042");
  });
});
