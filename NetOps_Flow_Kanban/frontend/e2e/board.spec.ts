import { test, expect } from "@playwright/test";
import {
  columnByKey,
  createCard,
  deleteCard,
  getBoard,
  moveCard,
  renameColumn,
  signIn,
} from "./board-api";

// Every card a test creates is titled "E2E ...", so teardown can sweep them
// even when the test failed before reaching its own cleanup.
let restoreColumn: { id: number; title: string } | null = null;

test.afterEach(async ({ request }) => {
  const token = await signIn(request);
  const board = await getBoard(request, token);
  for (const card of board.cards) {
    if (card.title.startsWith("E2E ")) {
      await deleteCard(request, token, card.id);
    }
  }
  if (restoreColumn) {
    await renameColumn(request, token, restoreColumn.id, restoreColumn.title);
    restoreColumn = null;
  }
});

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Username").fill("user");
  await page.getByLabel("Password").fill("password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Board" })).toBeVisible();
});

const COLUMN_KEYS = ["backlog", "in-progress", "cab", "deployed"];

test("loads the board with four columns and seeded cards", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Board" })).toBeVisible();
  // Columns are identified by key, since their titles are user-renamable.
  for (const key of COLUMN_KEYS) {
    await expect(
      page.locator(`[data-testid="column"][data-column-id="${key}"]`)
    ).toBeVisible();
  }
  await expect(page.getByText("CHG-1088")).toBeVisible();
});

test("shows stats tiles computed from seeded cards", async ({ page }) => {
  await expect(page.getByText("Open Change Requests")).toBeVisible();
  await expect(page.getByText("Active Incidents (P1/P2)")).toBeVisible();
  await expect(page.getByText("SLA at Risk")).toBeVisible();
  await expect(page.getByText("Deployments This Week")).toBeVisible();
});

test("filters visible cards as the user types in search", async ({ page }) => {
  const search = page.getByLabel("Search cards");
  await search.fill("DNS");
  await expect(page.getByText("Migrate DNS to new resolver cluster")).toBeVisible();
  await expect(page.getByText("Upgrade core switch firmware - DC2")).not.toBeVisible();

  await search.fill("CHG-1050");
  await expect(page.getByText("Patch edge firewalls - Q3 CVE batch")).toBeVisible();
});

test("adds a new card to a column via the add card form", async ({ page }) => {
  const title = `E2E add card ${Date.now()}`;
  const backlogColumn = page.locator('[data-testid="column"][data-column-id="backlog"]');
  await backlogColumn.getByRole("button", { name: "+ Add card" }).click();

  const dialog = page.locator("form");
  await page.getByLabel("Ticket prefix").selectOption("CHG");
  await page.getByLabel("Title").fill(title);
  await page.getByLabel("Category").selectOption("Network");
  await page.getByLabel("Priority").selectOption("P1");
  await page.getByLabel("Assignee").fill("nk");
  await page.getByLabel("Due date").fill("2026-12-01");
  await dialog.getByRole("button", { name: "Add card", exact: true }).click();

  const card = backlogColumn.locator('[data-testid="card"]').filter({ hasText: title });
  await expect(card).toBeVisible();
  await expect(card.getByTitle("NK")).toBeVisible();

});

test("deletes a card from the board", async ({ page, request }) => {
  const token = await signIn(request);
  const fixture = await createCard(request, token, "backlog", {
    title: "E2E card to delete",
  });
  await page.reload();

  const card = page.locator(`[data-testid="card"][data-ticket-id="${fixture.ticket_id}"]`);
  await expect(card).toBeVisible();
  await card.hover();
  await page.getByLabel(`Delete ${fixture.ticket_id}`).click();
  await expect(card).toHaveCount(0);
});

test("renames a column", async ({ page, request }) => {
  const token = await signIn(request);
  const backlog = await columnByKey(request, token, "backlog");
  const original = backlog.title;
  const renamed = `Intake ${Date.now()}`;

  await page.getByRole("heading", { name: original }).click();
  const input = page.getByLabel(`Rename ${original} column`);
  await input.fill(renamed);
  await input.press("Enter");

  restoreColumn = { id: backlog.id, title: original };

  await expect(page.getByRole("heading", { name: renamed })).toBeVisible();
  await expect(page.getByRole("heading", { name: original })).toHaveCount(0);
});

test("drags a card from backlog into in-progress", async ({ page, request }) => {
  const token = await signIn(request);
  const backlog = await columnByKey(request, token, "backlog");
  const fixture = await createCard(request, token, "backlog", {
    title: "E2E card to drag",
  });
  // Put it at the top so the drag starts from a point inside the viewport.
  await moveCard(request, token, fixture.id, backlog.id, 0);
  await page.reload();

  const card = page.locator(`[data-testid="card"][data-ticket-id="${fixture.ticket_id}"]`);
  const inProgressColumn = page.locator(
    '[data-testid="column"][data-column-id="in-progress"]'
  );

  await expect(card).toBeVisible();
  await card.scrollIntoViewIfNeeded();
  const cardBox = await card.boundingBox();
  const targetBox = await inProgressColumn.boundingBox();
  if (!cardBox || !targetBox) throw new Error("Could not measure elements");

  await page.mouse.move(cardBox.x + cardBox.width / 2, cardBox.y + cardBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + 60, {
    steps: 10,
  });
  await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + 70, {
    steps: 5,
  });
  await page.mouse.up();

  await expect(
    inProgressColumn.locator(`[data-testid="card"][data-ticket-id="${fixture.ticket_id}"]`)
  ).toBeVisible();

  // The move must survive a reload, not just live in optimistic local state.
  await page.reload();
  await expect(
    inProgressColumn.locator(`[data-testid="card"][data-ticket-id="${fixture.ticket_id}"]`)
  ).toBeVisible();
});
