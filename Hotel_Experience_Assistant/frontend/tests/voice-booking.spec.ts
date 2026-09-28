import { test, expect } from "@playwright/test";
import path from "node:path";

// Two spoken utterances in one WAV file, with a silence gap: (1) a booking
// request, (2) "yes, confirm" - drives create_booking's real propose->confirm
// cycle end to end (STT -> agent -> TTS -> card).
const bookingWav = path.resolve(
  __dirname,
  "../../backend/tests/fixtures/en_booking_request.wav"
);

test.use({
  launchOptions: {
    args: [
      "--use-fake-device-for-media-stream",
      "--use-fake-ui-for-media-stream",
      `--use-file-for-fake-audio-capture=${bookingWav}`,
    ],
  },
});

test("guest completes a booking by voice, propose then confirm", async ({
  page,
  context,
}) => {
  test.setTimeout(300_000);
  await context.grantPermissions(["microphone"]);
  await page.goto("/");

  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByText(/Listening|Speaking/)).toBeVisible();

  const captionParagraphs = page.getByTestId("captions").locator("p");

  // Guest caption from utterance 1 (the booking request).
  await expect(
    captionParagraphs.filter({ hasText: /book|standard|Alex/i }).first()
  ).toBeVisible({ timeout: 90_000 });

  // Assistant's propose-step summary (read out before any card is sent).
  await expect(
    captionParagraphs.filter({ hasText: /confirm|standard|book/i }).nth(1)
  ).toBeVisible({ timeout: 90_000 });

  // Guest's "yes" (utterance 2) drives the confirm step, which actually
  // executes create_booking and sends a card.
  const card = page.getByTestId("card");
  await expect(card).toBeVisible({ timeout: 120_000 });
  await expect(card).toContainText(/reference/i);
  // A real booking reference: 6 chars from booking_service's safe alphabet
  // (no 0/O/1/I/L), proving create_booking actually ran, not just text.
  // (No \b anchors: SummaryCard concatenates label+value with no separator,
  // e.g. "Reference5688PWRoom Type Code...", so word boundaries don't apply.)
  await expect(card).toContainText(/[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{6}/);

  await page.screenshot({
    path: "test-results/voice-booking-e2e.png",
    fullPage: true,
  });
});
