import {defineConfig} from '@playwright/test';

const port=Number(process.env.TV_TRACKER_TEST_PORT||8511);

export default defineConfig({
  testDir: './tests',
  // The compact sidebar retired Overview, Data Sheets and Activity navigation.
  // Retain legacy suites on disk; run current navigation and updater regressions.
  testMatch: ['desktop-updates.spec.js', 'workspace-report-sources.spec.js', 'workspace-appearance.spec.js', 'extraction-activity.spec.js', 'sla-compare.spec.js'],
  timeout: 45000,
  workers: 1,
  use: {baseURL: `http://127.0.0.1:${port}`, viewport: {width: 1440, height: 1000}, channel: 'chrome'},
  webServer: {command: `node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port ${port} --strictPort`, url: `http://127.0.0.1:${port}`, reuseExistingServer: false},
});
