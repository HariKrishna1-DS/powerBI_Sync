const puppeteer = require(process.env.DATATRACE_DESKTOP === '1' ? 'puppeteer-core' : 'puppeteer');
const fs = require('fs');
const path = require('path');
const {browserOptions} = require('./browser_options.cjs');

require('dotenv').config({ path: path.join(__dirname, '.env'), quiet: true });
const config = require('./sync_config.json');
const TARGET_URL = process.env.DATATRACE_QUEUE_URL || config.queue_url;
const USERNAME = process.env.DATATRACE_USERNAME;
const PASSWORD = process.env.DATATRACE_PASSWORD;
const TIMEOUT_MS = Number(process.env.DATATRACE_TIMEOUT_MS || 120000);
if (!USERNAME || !PASSWORD) {
    console.error('Set DATATRACE_USERNAME and DATATRACE_PASSWORD.');
    process.exit(1);
}

const outputPath = process.env.DATATRACE_OUTPUT_JSON || path.join(__dirname, 'queue_data.json');

(async () => {
    let browser;
    try {
        const options = browserOptions();
        const headless = options.headless;
        console.log(`[*] Launching Puppeteer Chromium Browser (headless=${headless}, timeout=${TIMEOUT_MS}ms)...`);
        console.log(`[*] Chromium executable: ${options.executablePath || await puppeteer.executablePath()}`);
        browser = await puppeteer.launch(options);
        console.log('[+] Chromium launched successfully.');

        const page = await browser.newPage();
        console.log(`[*] Navigating to: ${TARGET_URL}`);
        await page.goto(TARGET_URL, { waitUntil: 'domcontentloaded', timeout: TIMEOUT_MS }).catch(e => {
            console.log("[!] Navigation load notice:", e.message);
        });

        // Check for Azure B2C (#signInName) or ASP.NET login inputs
        let usernameSelector = '#signInName';
        let passwordSelector = '#password';
        let submitSelector = '#next';

        console.log("[*] Checking for login inputs...");
        await page.waitForSelector(usernameSelector, { timeout: TIMEOUT_MS }).catch(() => {});

        if (!await page.$(usernameSelector)) {
            if (await page.$('#txtUserName')) {
                usernameSelector = '#txtUserName';
                passwordSelector = '#txtPassword';
                submitSelector = '#btnSignIn';
            } else if (await page.$('[name*="UserName"]')) {
                usernameSelector = '[name*="UserName"]';
                passwordSelector = '[name*="Password"]';
                submitSelector = '[name*="Sign"], [name*="Login"], button[type="submit"]';
            }
        }

        const userElem = await page.$(usernameSelector);
        if (userElem) {
            console.log(`[*] Found login field (${usernameSelector}). Entering configured credentials`);

            // Focus and set value safely
            await page.evaluate((sel, val) => {
                const el = document.querySelector(sel);
                if (el) {
                    el.focus();
                    el.value = val;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }, usernameSelector, USERNAME);

            console.log("[*] Entering Password...");
            await page.evaluate((sel, val) => {
                const el = document.querySelector(sel);
                if (el) {
                    el.focus();
                    el.value = val;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }, passwordSelector, PASSWORD);

            console.log("[*] Clicking 'Sign in' button...");
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle2', timeout: TIMEOUT_MS }).catch(() => {}),
                page.evaluate(sel => {
                    const btn = document.querySelector(sel);
                    if (btn) btn.click();
                }, submitSelector)
            ]);
        } else {
            console.log("[*] No login inputs found or already logged in. Proceeding to target table...");
        }

        // Scope table discovery and paging to the portal's results panel.
        const GRID_SELECTOR = '#ctl00_ContentPlaceHolder1_pnlResults';

        console.log(`[*] Waiting for queue grid table selector: ${GRID_SELECTOR}...`);
        await page.waitForSelector(GRID_SELECTOR, { visible: true, timeout: TIMEOUT_MS });

        // A fresh login can show an empty results panel until Refresh View runs the query.
        const hasResults = await page.$(`${GRID_SELECTOR} table`);
        if (!hasResults) {
            const refresh = await page.$('input[value="Refresh View"]');
            if (!refresh) throw new Error('Results panel is empty and Refresh View was not found.');
            console.log('[*] Loading queue results with Refresh View...');
            await Promise.all([
                page.waitForFunction(selector => {
                    const panel = document.querySelector(selector);
                    return panel && panel.querySelector('table');
                }, { timeout: TIMEOUT_MS }, GRID_SELECTOR),
                refresh.click(),
            ]);
        }

        // Try clicking Arrival Time header to sort by newest arrival date
        try {
            const headers = await page.$$(`${GRID_SELECTOR} th`);
            for (const header of headers) {
                const text = await page.evaluate(el => el.textContent.trim(), header);
                if (text.toLowerCase().includes('arrival time')) {
                    console.log("[*] Sorting by Arrival Time header...");
                    await header.click();
                    await new Promise(r => setTimeout(r, 2000));
                    break;
                }
            }
        } catch (e) {
            console.log("[!] Header click sort note:", e.message);
        }

        // Locate the queue by its headers, not the first layout table in the panel.
        let tableData = [];
        const {advertisedCount, captureEvidence} = require('./capture_validation.cjs');
        let expectedRows = null;
        const seenPages = new Set();
        for (let pageNumber = 0; ; pageNumber++) {
        if (pageNumber >= 1000) throw new Error('Queue pagination exceeded safety limit.');
        const advertised = advertisedCount(await page.$eval(GRID_SELECTOR, el => [...el.querySelectorAll('.rgInfoPart')].map(node => node.textContent).join(' ')));
        if (advertised !== null) {
            if (expectedRows !== null && expectedRows !== advertised) throw new Error('Queue totals changed during extraction. Retry a fresh capture.');
            expectedRows = advertised;
        }
        const pageData = await page.evaluate((selector) => {
            const gridContainer = document.querySelector(selector);

            if (!gridContainer) return null;

            const tables = gridContainer.tagName === 'TABLE'
                ? [gridContainer, ...gridContainer.querySelectorAll('table')]
                : [...gridContainer.querySelectorAll('table')];
            const targetTable = tables.find(table => [...table.rows].some(row => {
                const names = [...row.cells].map(cell => cell.textContent.trim().replace(/\s+/g, ' '));
                return names.includes('Arrival Time') && names.includes('Task Status');
            }));

            if (!targetTable) return null;

            const rows = Array.from(targetTable.rows);
            if (!rows.length) return null;

            // Extract column headers from top row / thead
            let headers = [];
            const headerRow = rows.find(row => {
                const names = [...row.cells].map(cell => cell.textContent.trim().replace(/\s+/g, ' '));
                return names.includes('Arrival Time') && names.includes('Task Status');
            });
            if (headerRow) {
                headers = Array.from(headerRow.cells).map(cell => cell.textContent.trim().replace(/\s+/g, ' '));
            }

            const records = [];
            for (const row of rows) {
                // Skip header row and pager row
                if (row === headerRow || row.classList.contains('rgPager') || row.querySelector('th') || row.classList.contains('rgFilterRow')) continue;

                const cells = Array.from(row.cells);
                if (!cells.length || cells.length !== headers.length) continue;

                // Skip if row is pager
                if (row.closest('.rgPager') || cells.some(c => c.classList.contains('rgPagerCell'))) continue;

                const rowObj = {};
                cells.forEach((cell, idx) => {
                    const colName = headers[idx] || `Column_${idx + 1}`;
                    rowObj[colName] = cell.textContent.trim().replace(/\s+/g, ' ');
                });

                if (Object.keys(rowObj).length > 0 && Object.values(rowObj).some(val => val !== "")) {
                    records.push(rowObj);
                }
            }
            if (!headers.includes('Arrival Time') || !headers.includes('Task Status')) return null;
            return records;
        }, GRID_SELECTOR);
        if (!pageData || !pageData.length) {
            if (process.env.DATATRACE_DIAGNOSTICS_DIR) {
                const folder = process.env.DATATRACE_DIAGNOSTICS_DIR;
                fs.mkdirSync(folder, {recursive: true});
                fs.writeFileSync(path.join(folder, 'results-panel.html'),
                    await page.$eval(GRID_SELECTOR, el => el.outerHTML), 'utf8');
                await page.screenshot({path: path.join(folder, 'results-panel.png'), fullPage: true});
            }
            throw new Error(`Queue table missing or empty inside ${GRID_SELECTOR}.`);
        }
        const fingerprint = JSON.stringify(pageData);
        if (seenPages.has(fingerprint)) throw new Error('Queue pagination repeated a page.');
        seenPages.add(fingerprint);
        tableData.push(...pageData);
        const nextSelector = `${GRID_SELECTOR} .rgPageNext`;
        const next = await page.$(nextSelector);
        const enabled = next && await page.evaluate(el =>
            !el.disabled && el.getAttribute('aria-disabled') !== 'true' &&
            !el.className.includes('Disabled'), next);
        if (!enabled) break;
        const before = await page.$eval(GRID_SELECTOR, el => el.innerText);
        await next.click();
        await page.waitForFunction((selector, previous) => {
            const grid = document.querySelector(selector);
            return grid && grid.innerText !== previous;
        }, { timeout: TIMEOUT_MS }, GRID_SELECTOR, before);
        await new Promise(resolve => setTimeout(resolve, 500));
        }

        if (tableData && tableData.length > 0) {
            console.log(`[+] Successfully extracted ${tableData.length} queue rows from ${GRID_SELECTOR}!`);

            // Clean up unneeded empty columns (like Column_1) before exporting
            const cleanedData = tableData.map(row => {
                const newRow = {};
                Object.keys(row).forEach(k => {
                    if (k && !k.toLowerCase().startsWith('column_1') && k.trim() !== '') {
                        newRow[k] = row[k];
                    } else if (row[k] && row[k].trim() !== '') {
                        newRow[k] = row[k];
                    }
                });
                return newRow;
            });

            const evidence = captureEvidence(cleanedData, expectedRows, seenPages.size);
            fs.writeFileSync(outputPath, JSON.stringify(cleanedData), 'utf8');
            if (process.env.DATATRACE_OUTPUT_META) fs.writeFileSync(process.env.DATATRACE_OUTPUT_META, JSON.stringify(evidence), 'utf8');
            console.log(`[+] Queue extracted. Python pipeline exports CSV/Excel and syncs spreadsheet ${config.spreadsheet_id}.`);
        } else {
            throw new Error("No queue records extracted.");
        }

    } catch (err) {
        console.error("[!] Puppeteer Automation Error:", err.stack || err.message);
        process.exitCode = 1;
    } finally {
        if (browser) await browser.close();
        console.log("[*] Browser closed. Scraping process finished.");
    }
})().catch(err => { console.error(err.stack || err.message); process.exitCode = 1; });
