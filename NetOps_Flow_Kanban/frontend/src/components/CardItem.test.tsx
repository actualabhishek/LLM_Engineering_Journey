import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DndContext } from "@dnd-kit/core";
import { CardItem } from "./CardItem";
import type { CardData } from "@/lib/types";

function renderCard(card: CardData, onDelete = vi.fn()) {
  return {
    onDelete,
    ...render(
      <DndContext>
        <CardItem card={card} onDelete={onDelete} />
      </DndContext>
    ),
  };
}

const baseCard: CardData = {
  id: "card-1",
  ticketId: "CHG-1050",
  title: "Patch edge firewalls",
  category: "Security",
  priority: "P1",
  assignee: "AS",
  dueDate: "2026-09-25",
  columnId: "backlog",
};

describe("CardItem", () => {
  it("renders ticket id, title, category and priority", () => {
    renderCard(baseCard);
    expect(screen.getByText("CHG-1050")).toBeInTheDocument();
    expect(screen.getByText("Patch edge firewalls")).toBeInTheDocument();
    expect(screen.getByText("Security")).toBeInTheDocument();
    expect(screen.getByText("P1")).toBeInTheDocument();
    expect(screen.getByText("Due Sep 25, 2026")).toBeInTheDocument();
  });

  it("shows a progress bar only for in-progress cards", () => {
    renderCard({ ...baseCard, columnId: "in-progress", progress: 42 });
    expect(screen.getByText("42%")).toBeInTheDocument();
  });

  it("shows CAB approval badge and maintenance window instead of due date", () => {
    renderCard({ ...baseCard, columnId: "cab" });
    expect(screen.getByText("Awaiting CAB approval")).toBeInTheDocument();
    expect(screen.queryByText(/^Due /)).not.toBeInTheDocument();
  });

  it("calls onDelete with the card id when the delete button is clicked", async () => {
    const onDelete = vi.fn();
    renderCard(baseCard, onDelete);
    await userEvent.click(screen.getByLabelText("Delete CHG-1050"));
    expect(onDelete).toHaveBeenCalledWith("card-1");
  });
});
