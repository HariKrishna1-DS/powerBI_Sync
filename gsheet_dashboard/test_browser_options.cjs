const assert = require('node:assert/strict');
const {browserOptions} = require('./browser_options.cjs');

const desktop = browserOptions({}, 'win32');
assert.equal(desktop.headless, true);
assert.equal(desktop.args.includes('--no-sandbox'), false);
assert.equal(browserOptions({}, 'linux').args.includes('--no-sandbox'), false);
const container = browserOptions({DATATRACE_CHROME_NO_SANDBOX:'true', PUPPETEER_EXECUTABLE_PATH:'/usr/bin/chromium'}, 'linux');
assert.equal(container.executablePath, '/usr/bin/chromium');
assert.ok(container.args.includes('--no-sandbox'));
assert.ok(container.args.includes('--disable-dev-shm-usage'));
assert.equal(browserOptions({DATATRACE_CHROME_NO_SANDBOX:'true'}, 'win32').args.includes('--no-sandbox'), false);
assert.equal(browserOptions({DATATRACE_HEADLESS:'false'}, 'win32').headless, false);
console.log('PASS: container browser options and sandboxed desktop defaults');
