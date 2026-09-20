import { test, expect } from "@playwright/test";

test("shows an error on invalid credentials", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Username").fill("user");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByText("Invalid username or password")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Board" })).not.toBeVisible();
});

test("signs in with valid credentials and reaches the board", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Username").fill("user");
  await page.getByLabel("Password").fill("password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("heading", { name: "Board" })).toBeVisible();
});

test("persists the session across a page reload", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Username").fill("user");
  await page.getByLabel("Password").fill("password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Board" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Board" })).toBeVisible();
});
