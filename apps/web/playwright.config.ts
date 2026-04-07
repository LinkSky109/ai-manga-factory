import fs from "node:fs";

import { defineConfig } from "@playwright/test";

const EDGE_EXECUTABLE_PATH = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
const hasSystemEdge = fs.existsSync(EDGE_EXECUTABLE_PATH);

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    browserName: "chromium",
    channel: hasSystemEdge ? "msedge" : undefined,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "off",
  },
  webServer: {
    command: "npm run preview",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: true,
    timeout: 120000,
  },
});
