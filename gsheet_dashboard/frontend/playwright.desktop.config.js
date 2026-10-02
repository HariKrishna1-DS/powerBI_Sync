import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  testMatch: ['desktop-ui.spec.js', 'desktop-alignment.spec.js', 'desktop-updates.spec.js'],
  timeout: 45000,
  workers: 1,
  use: {baseURL: 'http://127.0.0.1:8511', viewport: {width: 1440, height: 1000}, channel: 'chrome'},
  webServer: {command: 'npm run dev -- --port 8511 --strictPort', url: 'http://127.0.0.1:8511', reuseExistingServer: false},
});
