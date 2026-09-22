import { defineConfig } from '@playwright/test';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const puppeteer = require('../node_modules/puppeteer');
export default defineConfig({
  testDir: './tests', timeout: 45000, workers: 1,
  use: { baseURL: 'http://localhost:8510', viewport: {width:1440,height:1000},
    launchOptions: {executablePath: await puppeteer.executablePath()} },
});
