import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AddCardModal } from "./AddCardModal";

describe("AddCardModal", () => {
  it("submits a new card with a generated ticket id", async () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(
      <AddCardModal
        columnId="backlog"
        allCards={[]}
        onClose={onClose}
        onSubmit={onSubmit}
      />
    );

    await userEvent.selectOptions(screen.getByLabelText("Ticket prefix"), "CHG");
    await userEvent.type(screen.getByLabelText("Title"), "Rotate TLS certificates");
    await userEvent.selectOptions(screen.getByLabelText("Category"), "Security");
    await userEvent.selectOptions(screen.getByLabelText("Priority"), "P2");
    await userEvent.type(screen.getByLabelText("Assignee"), "mk");
    await userEvent.type(screen.getByLabelText("Due date"), "2026-10-01");
    await userEvent.click(screen.getByRole("button", { name: "Add card" }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        ticketId: "CHG-1001",
        title: "Rotate TLS certificates",
        category: "Security",
        priority: "P2",
        assignee: "MK",
        dueDate: "2026-10-01",
        columnId: "backlog",
      })
    );
  });

  it("does not submit when required fields are missing", async () => {
    const onSubmit = vi.fn();
    render(
      <AddCardModal
        columnId="backlog"
        allCards={[]}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: "Add card" }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("calls onClose when cancel is clicked", async () => {
    const onClose = vi.fn();
    render(
      <AddCardModal
        columnId="backlog"
        allCards={[]}
        onClose={onClose}
        onSubmit={vi.fn()}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalled();
  });
});
