const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const puppeteer = require('puppeteer');

// Run the actual scraper against an isolated two-page portal fixture.
(async () => {
    const browser = await puppeteer.launch({headless: true});
    const originalNewPage = browser.newPage.bind(browser);
    browser.newPage = async () => {
        const page = await originalNewPage();
        await page.setRequestInterception(true);
        page.on('request', request => request.respond({contentType: 'text/html', body: `
            <table><tr><th>Arrival Time</th><th>Task Status</th></tr><tr><td>outside</td><td>wrong</td></tr></table>
            <div id="ctl00_ContentPlaceHolder1_pnlResults">
              <table><tr><td>Layout only</td></tr></table>
              <table><thead><tr><td>Arrival Time</td><td>Task Status</td><td>OPON</td></tr></thead>
                <tbody><tr><td>09/22/2026 01:00 PM</td><td>Available</td><td id="task">001</td></tr></tbody>
              </table>
              <button class="rgPageNext" onclick="document.getElementById('task').textContent='002';this.disabled=true">Next</button>
            </div>`}));
        return page;
    };
    let captured;
    const fakeProcess = {env: {DATATRACE_USERNAME: 'fixture', DATATRACE_PASSWORD: 'fixture', DATATRACE_TIMEOUT_MS: '30000'}, exitCode: 0};
    try {
        await vm.runInNewContext(fs.readFileSync(path.join(__dirname, 'scrape_datatrace.js'), 'utf8'), {
            __dirname, console, setTimeout, process: fakeProcess,
            require(name) {
                if (name === 'puppeteer') return {launch: async () => browser, executablePath: () => puppeteer.executablePath()};
                if (name === './browser_options.cjs') return {browserOptions: () => require('./browser_options.cjs').browserOptions(fakeProcess.env, process.platform)};
                if (name === 'dotenv') return {config() {}};
                if (name === 'fs') return {writeFileSync: (_path, data) => {captured = JSON.parse(data);}};
                return require(name);
            },
        });
        assert.equal(fakeProcess.exitCode, 0);
        assert.deepEqual(captured.map(row => row.OPON), ['001', '002']);
        assert.equal(captured[0]['Task Status'], 'Available');
        console.log('PASS: results-panel selection, decoy exclusion and two-page extraction');
    } finally {
        await browser.close();
    }
})().catch(error => {console.error(error); process.exitCode = 1;});
