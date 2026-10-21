const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const puppeteer = require('puppeteer');

// Run the actual scraper against an isolated two-page portal fixture.
(async () => {
    const fullEta = 'ETA: Order has been assigned to the abstractor, and we will ensure completion within SLA.';
    const nextEta = 'ETA: Hello, we apologize for the delay.\nWe will send the complete update shortly.';
    const fullComment = 'Continue - Full review details that are only present in the tooltip.';
    const describedComment = 'Additional comment details including the complete second paragraph.';
    const browser = await puppeteer.launch({headless: true,
        executablePath:process.env.PUPPETEER_EXECUTABLE_PATH || await puppeteer.executablePath()});
    const originalNewPage = browser.newPage.bind(browser);
    browser.newPage = async () => {
        const page = await originalNewPage();
        await page.setRequestInterception(true);
        page.on('request', request => request.respond({contentType: 'text/html', body: `
            <table><tr><th>Arrival Time</th><th>Task Status</th></tr><tr><td>outside</td><td>wrong</td></tr></table>
            <div id="ctl00_ContentPlaceHolder1_pnlResults">
              <table><tr><td>Layout only</td></tr></table>
              <table><thead><tr><td>Arrival Time</td><td>Task Status</td><td>OPON</td><td>ETA Comments</td><td>Comment</td><td>Comments</td><td>Product</td></tr></thead>
                <tbody><tr><td>09/22/2026 01:00 PM</td><td>Available</td><td id="task" title="Open order overview">001</td>
                  <td id="eta" title="${fullEta}">ETA: Order has been assigned to the abst.</td>
                  <td><span data-original-title="${fullComment}">Continue - Full review..</span></td>
                  <td title="Unrelated action label that must not become the comment"><span aria-describedby="comment-details">Additional comment..</span></td>
                  <td title="Product details are not a comment">ClientRev..</td>
                </tr></tbody>
              </table>
              <button class="rgPageNext" onclick="advance();this.disabled=true">Next</button>
            </div><div id="comment-details" hidden>${describedComment}</div><script>
              window.nextEta=${JSON.stringify(nextEta)};
              function advance(){
                document.getElementById('task').textContent='002';
                const eta=document.getElementById('eta');eta.removeAttribute('title');
                const span=document.createElement('span');span.setAttribute('data-tooltip-content',window.nextEta);
                span.textContent='ETA: Hello, we apol..';eta.replaceChildren(span);
              }
            </script>`}));
        return page;
    };
    let captured;
    const fakeProcess = {env: {DATATRACE_DESKTOP:'1', PUPPETEER_EXECUTABLE_PATH:browser.process().spawnfile,
        DATATRACE_USERNAME: 'fixture', DATATRACE_PASSWORD: 'fixture', DATATRACE_TIMEOUT_MS: '30000'}, exitCode: 0};
    try {
        await vm.runInNewContext(fs.readFileSync(path.join(__dirname, 'scrape_datatrace.js'), 'utf8'), {
            __dirname, console, setTimeout, process: fakeProcess,
            require(name) {
                if (name === 'puppeteer-core') return {launch: async () => browser};
                if (name === './sync_config.json') return {queue_url:'https://portal.fixture.invalid/queues',spreadsheet_id:'fixture-sheet'};
                if (name === './browser_options.cjs') return {browserOptions: () => require('./browser_options.cjs').browserOptions(fakeProcess.env, process.platform)};
                if (name === 'dotenv') return {config() {}};
                if (name === 'fs') return {writeFileSync: (_path, data) => {captured = JSON.parse(data);}};
                return require(name);
            },
        });
        assert.equal(fakeProcess.exitCode, 0);
        assert.deepEqual(captured.map(row => row.OPON), ['001', '002']);
        assert.equal(captured[0]['Task Status'], 'Available');
        assert.equal(captured[0]['ETA Comments'], fullEta);
        assert.equal(captured[1]['ETA Comments'], nextEta);
        assert.ok(captured.every(row => row.Comment === fullComment));
        assert.ok(captured.every(row => row.Comments === describedComment));
        assert.ok(captured.every(row => row.Product === 'ClientRev..'));
        console.log('PASS: results-panel selection, two-page extraction, complete tooltip comments, and preserved order IDs');
    } finally {
        await browser.close();
    }
})().catch(error => {console.error(error); process.exitCode = 1;});
