const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');
const XLSX = require('xlsx');

const TARGET_URL = "https://tv.datatracetitle.com/Queues.aspx?qid=23656";
const USERNAME = "KishoreK_ADS";
const PASSWORD = "Kishore@2025";

const csvPath = path.join(__dirname, 'queue_data_sheet2.csv');
const excelPath = path.join(__dirname, 'queue_data_sheet2.xlsx');

(async () => {
    console.log("[*] Launching Puppeteer Chromium Browser...");
    const browser = await puppeteer.launch({
        headless: false, // Visible browser so user can see auto login in action
        defaultViewport: null,
        args: ['--start-maximized', '--no-sandbox', '--disable-setuid-sandbox']
    });

    try {
        const page = await browser.newPage();
        console.log(`[*] Navigating to: ${TARGET_URL}`);
        await page.goto(TARGET_URL, { waitUntil: 'networkidle2', timeout: 45000 });

        // Check if redirected to Azure B2C login screen (#signInName)
        const usernameSelector = '#signInName';
        const passwordSelector = '#password';
        const submitSelector = '#next';

        console.log("[*] Checking for login inputs...");
        await page.waitForSelector(usernameSelector, { timeout: 15000 }).catch(() => {
            console.log("[!] Login fields not immediately found, checking alternative forms...");
        });

        if (await page.$(usernameSelector)) {
            console.log(`[*] Entering Username: ${USERNAME}`);
            await page.click(usernameSelector);
            await page.type(usernameSelector, USERNAME, { delay: 50 });

            console.log("[*] Entering Password...");
            await page.click(passwordSelector);
            await page.type(passwordSelector, PASSWORD, { delay: 50 });

            console.log("[*] Clicking 'Sign in' button (#next)...");
            await Promise.all([
                page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {}),
                page.click(submitSelector)
            ]);
        }

        console.log("[*] Waiting for queue table data...");
        await page.waitForSelector('table', { timeout: 30000 }).catch(() => {
            console.log("[!] Table timeout. Capturing visible table data if available...");
        });

        // Try clicking Arrival Time header to sort by newest arrival date
        try {
            const headers = await page.$$('th, td');
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

        // Parse Table Data from Page DOM
        const tableData = await page.evaluate(() => {
            const tables = Array.from(document.querySelectorAll('table'));
            if (!tables.length) return null;

            // Pick table with most rows
            let targetTable = tables[0];
            let maxRows = 0;
            for (const t of tables) {
                const rCount = t.querySelectorAll('tr').length;
                if (rCount > maxRows) {
                    maxRows = rCount;
                    targetTable = t;
                }
            }

            const rows = Array.from(targetTable.querySelectorAll('tr'));
            if (!rows.length) return null;

            // Extract column headers
            const headerRow = rows[0];
            const headers = Array.from(headerRow.querySelectorAll('th, td')).map(cell => cell.textContent.trim());

            const records = [];
            for (let i = 1; i < rows.length; i++) {
                const cells = Array.from(rows[i].querySelectorAll('td'));
                if (!cells.length) continue;

                const rowObj = {};
                cells.forEach((cell, idx) => {
                    const colName = headers[idx] || `Column_${idx + 1}`;
                    rowObj[colName] = cell.textContent.trim();
                });
                records.push(rowObj);
            }
            return records;
        });

        if (tableData && tableData.length > 0) {
            console.log(`[+] Extracted ${tableData.length} queue rows!`);

            // Write CSV
            const worksheet = XLSX.utils.json_to_sheet(tableData);
            const csvContent = XLSX.utils.sheet_to_csv(worksheet);
            fs.writeFileSync(csvPath, csvContent, 'utf8');

            // Write Excel with Sheet2
            const workbook = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(workbook, worksheet, "Sheet2");
            XLSX.writeFile(workbook, excelPath);

            console.log(`[+] Saved queue data to: ${csvPath}`);
            console.log(`[+] Saved queue data to: ${excelPath}`);
        } else {
            console.log("[!] No table data extracted from page DOM.");
        }

    } catch (err) {
        console.error("[!] Puppeteer Automation Error:", err.message);
    } finally {
        await browser.close();
        console.log("[*] Browser closed. Scraping process finished.");
    }
})();
