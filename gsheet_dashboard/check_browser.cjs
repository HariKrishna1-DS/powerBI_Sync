const puppeteer = require('puppeteer');
const {browserOptions} = require('./browser_options.cjs');

(async () => {
    const options = browserOptions();
    console.log(`Checking Chromium: ${options.executablePath || await puppeteer.executablePath()}`);
    const browser = await puppeteer.launch(options);
    try {
        const page = await browser.newPage();
        await page.setContent('<title>Browser check</title>');
        if (await page.title() !== 'Browser check') throw new Error('Browser page check failed');
        console.log(`Chromium check passed: ${await browser.version()}`);
    } finally {
        await browser.close();
    }
})().catch(error => {console.error(error); process.exitCode = 1;});
