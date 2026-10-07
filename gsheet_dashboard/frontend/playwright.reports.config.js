import {defineConfig} from '@playwright/test';

// Self-contained report tests serve the built assets through mocked routes.
// Use the installed Windows browser; no backend or Google credentials are needed.
export default defineConfig({
  testDir:'./tests', testMatch:'pdf-reports.spec.js', timeout:45000, workers:1,
  use:{channel:'msedge',viewport:{width:1440,height:1000}},
});
