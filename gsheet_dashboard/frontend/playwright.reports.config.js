import {defineConfig} from '@playwright/test';

// Self-contained report tests serve the built assets through mocked routes.
// Use the installed Windows browser; no backend or Google credentials are needed.
export default defineConfig({
  testDir:'./tests', testMatch:['pdf-reports.spec.js','sla-status.spec.js','sla-preview.spec.js','sla-comments.spec.js','changes-cards.spec.js','date-order-details.spec.js',
    'sla-manual.spec.js','sla-import-manual.spec.js','report-order-search.spec.js','table-filters.spec.js','sla-arrival-dates.spec.js','completion-status.spec.js'], timeout:45000, workers:1,
  use:{channel:'msedge',baseURL:'http://127.0.0.1:8534',viewport:{width:1440,height:1000}},
  webServer:{command:'node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 8534 --strictPort',url:'http://127.0.0.1:8534',reuseExistingServer:false},
});
