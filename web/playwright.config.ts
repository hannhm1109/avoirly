import { defineConfig } from "@playwright/test";
import path from "node:path";
const root = path.resolve(__dirname, "..");
const python =
  process.platform === "win32"
    ? "backend/.venv/Scripts/python.exe"
    : "backend/.venv/bin/python";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  timeout: 90000,
  expect: { timeout: 20000 },
  use: {
    baseURL: "http://127.0.0.1:3001",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 1050 },
  },
  webServer: [
    {
      command: `"${path.join(root, python)}" scripts/e2e-server.py`,
      cwd: root,
      url: "http://127.0.0.1:8001/api/v1/health",
      reuseExistingServer: false,
      timeout: 90000,
    },
    {
      command: "npm run dev -- --port 3001",
      url: "http://127.0.0.1:3001",
      env: { AVOIRLY_E2E: "1", AVOIRLY_API_ORIGIN: "http://127.0.0.1:8001" },
      reuseExistingServer: false,
      timeout: 120000,
    },
  ],
});
