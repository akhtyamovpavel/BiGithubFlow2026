import fs from "node:fs"
import { chromium, defineConfig, devices } from "@playwright/test"

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:8080"

function resolveExecutablePath(): string | undefined {
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) {
    return process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
  }
  try {
    const defaultPath = chromium.executablePath()
    if (defaultPath && fs.existsSync(defaultPath)) {
      return undefined
    }
  } catch {
    // Fallback to system Chrome below
  }
  if (fs.existsSync("/usr/bin/google-chrome")) {
    return "/usr/bin/google-chrome"
  }
  return undefined
}

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    headless: false,
    screenshot: "only-on-failure",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        headless: false,
        launchOptions: { executablePath: resolveExecutablePath() },
      },
    },
  ],
})
