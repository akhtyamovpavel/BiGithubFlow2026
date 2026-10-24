import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import { chromium, defineConfig, devices } from "@playwright/test"

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:8080"
const slowMo = Number(process.env.PLAYWRIGHT_SLOW_MO || "150")

function ensureFfmpegBinary(): void {
  const pwFfmpegDir = path.join(os.homedir(), ".cache", "ms-playwright", "ffmpeg-1013")
  const pwFfmpegBin = path.join(pwFfmpegDir, "ffmpeg-linux")
  if (!fs.existsSync(pwFfmpegBin) && fs.existsSync("/usr/bin/ffmpeg")) {
    try {
      fs.mkdirSync(pwFfmpegDir, { recursive: true })
      fs.symlinkSync("/usr/bin/ffmpeg", pwFfmpegBin)
    } catch {
      // Ignore if cache directory is not writable
    }
  }
}

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

ensureFfmpegBinary()

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
    viewport: { width: 1280, height: 720 },
    screenshot: "only-on-failure",
    trace: "on-first-retry",
    video: {
      mode: "on",
      size: { width: 1280, height: 720 },
    },
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        headless: false,
        viewport: { width: 1280, height: 720 },
        launchOptions: {
          executablePath: resolveExecutablePath(),
          slowMo,
        },
      },
    },
  ],
})
