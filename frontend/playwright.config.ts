import { defineConfig } from '@playwright/test'

// The stack is started outside Playwright (see docker-compose.e2e.yml); the journey is one
// ordered scenario, so it runs in a single worker.
export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8000',
    trace: 'retain-on-failure',
  },
})
