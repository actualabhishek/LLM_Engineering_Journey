import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:8000",
    trace: "on-first-retry",
  },
  // Same-origin proof: FastAPI serves the built frontend (frontend/out copied
  // into backend/app/static/, exactly like the Dockerfile) and /ws/voice
  // live, on one origin - `next dev` alone can't reach /ws/voice at all.
  // Start it yourself first (build + copy static + migrate/seed a throwaway
  // DB + uvicorn on :8000, mirroring scripts/entrypoint.sh) and leave it
  // running; Playwright reuses it via the health check below.
  webServer: {
    command:
      "node -e \"console.error('Start the full-stack FastAPI server first (see docs/progress.md Phase 5).'); process.exit(1)\"",
    url: "http://127.0.0.1:8000/health",
    reuseExistingServer: true,
    timeout: 20_000,
  },
});
