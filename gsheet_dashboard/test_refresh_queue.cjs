const {test} = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const puppeteer = require('../desktop/extractor/node_modules/puppeteer-core');
const {browserOptions} = require('./browser_options.cjs');
const {refreshQueue} = require('./refresh_queue.cjs');

test('refresh replaces an existing stale task before capture for native and AJAX views', async () => {
    let posts = 0;
    const table = status => `<div id="queue"><table><tr><th>Arrival Time</th><th>Task Status</th></tr><tr><td>10/29/2026</td><td>${status}</td></tr></table></div>`;
    const server = http.createServer((req, res) => {
        let body = '';
        req.on('data', chunk => {body += chunk;});
        req.on('end', () => {
            res.setHeader('Content-Type', 'text/html');
            if (req.method === 'POST') {
                posts++;
                if (req.url === '/native') assert.match(body, /refresh=Refresh\+View/);
                // Delay the response to expose premature readiness on old tables.
                setTimeout(() => res.end(table('Available')), 200);
            } else if (req.url === '/current') {
                res.end(table('Available'));
            } else if (req.url === '/get') {
                res.end(`<input type="button" value="Refresh View" onclick="location.href='/current'">${table('Workflow Suspended')}`);
            } else if (req.url === '/native') {
                res.end(`<form method="POST"><input name="refresh" type="submit" value="Refresh View"></form>${table('Workflow Suspended')}`);
            } else if (req.url === '/ajax') {
                res.end(`<input type="button" value="Refresh View" onclick="fetch('/ajax',{method:'POST'}).then(r=>r.text()).then(html=>document.querySelector('#queue').outerHTML=html)">${table('Workflow Suspended')}`);
            } else res.end(table('Workflow Suspended'));
        });
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const browser = await puppeteer.launch({...browserOptions(), headless: true});
    try {
        const page = await browser.newPage();
        const origin = `http://127.0.0.1:${server.address().port}`;
        for (const view of ['native', 'ajax', 'get']) {
            await page.goto(`${origin}/${view}`);
            assert.match(await page.$eval('#queue', el => el.textContent), /Workflow Suspended/);
            await refreshQueue(page, '#queue', 10000);
            assert.match(await page.$eval('#queue', el => el.textContent), /Available/);
        }
        assert.equal(posts, 2);
        await page.goto(`${origin}/missing`);
        await assert.rejects(refreshQueue(page, '#queue', 10000), /refusing to capture/);
    } finally {
        await browser.close();
        await new Promise(resolve => server.close(resolve));
    }
});
