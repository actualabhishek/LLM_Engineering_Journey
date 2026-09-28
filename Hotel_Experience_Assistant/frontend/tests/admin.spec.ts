import { test, expect } from "@playwright/test";

test("admin logs in, views data, logs out", async ({ page }) => {
  await page.goto("/admin");

  const loginForm = page.getByTestId("admin-login");
  await expect(loginForm).toBeVisible();

  await loginForm.locator('input[type="password"]').fill("wrong-password");
  await loginForm.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByText("Incorrect password")).toBeVisible();
  await expect(page.getByTestId("bookings-table")).not.toBeVisible();

  const adminPassword = process.env.ADMIN_PASSWORD;
  expect(adminPassword, "ADMIN_PASSWORD must be set to run this test").toBeTruthy();

  await loginForm.locator('input[type="password"]').fill(adminPassword!);
  await loginForm.getByRole("button", { name: "Log in" }).click();

  const bookingsTable = page.getByTestId("bookings-table");
  await expect(bookingsTable).toBeVisible();
  await expect(bookingsTable.locator("tbody tr")).not.toHaveCount(0);

  const conversationsTable = page.getByTestId("conversations-table");
  const noConversations = page.getByText("No conversations yet");
  await expect(conversationsTable.or(noConversations)).toBeVisible();

  const firstConversationView = conversationsTable
    .locator("tbody tr")
    .first()
    .getByRole("button", { name: "View" });
  if (await firstConversationView.isVisible().catch(() => false)) {
    await firstConversationView.click();
    await expect(page.getByTestId("transcript")).toBeVisible();
  }

  await page.screenshot({
    path: "test-results/admin-e2e.png",
    fullPage: true,
  });

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(loginForm).toBeVisible();
});
