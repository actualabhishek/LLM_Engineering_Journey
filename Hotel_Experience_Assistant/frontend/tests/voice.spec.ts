import { test, expect } from "@playwright/test";
import path from "node:path";

const fixtureWav = path.resolve(
  __dirname,
  "../../backend/tests/fixtures/en_sample.wav"
);

test.use({
  launchOptions: {
    args: [
      "--use-fake-device-for-media-stream",
      "--use-fake-ui-for-media-stream",
      `--use-file-for-fake-audio-capture=${fixtureWav}`,
    ],
  },
});

test("guest completes a voice turn", async ({ page, context }) => {
  await context.grantPermissions(["microphone"]);
  await page.goto("/");

  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByText(/Listening|Speaking/)).toBeVisible();

  await expect(page.getByTestId("captions").locator("p").first()).toBeVisible({
    timeout: 30_000,
  });

  await page.screenshot({
    path: "test-results/voice-e2e.png",
    fullPage: true,
  });
});
