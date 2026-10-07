import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  testMatch: ['release-281.spec.js', 'shared-source.spec.js', 'shared-workspace.spec.js', 'sheets-quota.spec.js', 'report-workspace.spec.js', 'upgrade-workspace.spec.js', 'desktop-ui.spec.js', 'desktop-alignment.spec.js', 'desktop-updates.spec.js',
    'tracker-v2.spec.js', 'october-updates.spec.js', 'sla-comments.spec.js', 'studio-workspace.spec.js', 'production-sync.spec.js', 'live-sheet-refresh.spec.js', 'sync-performance.spec.js', 'monthly-production.spec.js', 'workspace-redesign.spec.js'],
  timeout: 45000,
  workers: 1,
  use: {baseURL: 'http://127.0.0.1:8511', viewport: {width: 1440, height: 1000}, channel: 'chrome'},
  webServer: {command: 'npm run dev -- --port 8511 --strictPort', url: 'http://127.0.0.1:8511', reuseExistingServer: false},
});
