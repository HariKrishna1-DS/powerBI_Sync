import { defineConfig } from '@playwright/test';

const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
export default defineConfig({
  testDir: './tests', testMatch: 'production-sync.spec.js', workers: 1, timeout: 30000,
  use: {
    baseURL: 'http://127.0.0.1:8533', viewport: {width: 1440, height: 1000},
    channel: executablePath ? undefined : 'chrome',
    launchOptions: executablePath ? {executablePath} : {},
  },
  webServer: {
    command: 'node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 8533',
    url: 'http://127.0.0.1:8533', reuseExistingServer: false,
  },
});
