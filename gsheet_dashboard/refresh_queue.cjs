/** Run the portal query even when a previously rendered table is present. */
async function refreshQueue(page, selector, timeout) {
    const refresh = await page.$('input[value="Refresh View"]');
    if (!refresh) throw new Error('Refresh View was not found; refusing to capture potentially stale queue results.');
    const nativeSubmit = await page.evaluate(el => el.type === 'submit' && !!el.name && !!el.form, refresh);
    console.log(`[*] Refresh View: ${nativeSubmit ? 'native form postback' : 'button request'}`);
    let response;
    if (nativeSubmit) {
        // Use the same ASP.NET submit-button postback as the pager. Waiting for
        // navigation prevents an existing table from satisfying readiness early.
        [response] = await Promise.all([
            page.waitForNavigation({waitUntil: 'domcontentloaded', timeout}),
            page.evaluate(el => {
                const form = el.form;
                const button = document.createElement('input');
                button.type = 'hidden'; button.name = el.name; button.value = el.value;
                form.appendChild(button);
                for (const name of ['__EVENTTARGET', '__EVENTARGUMENT']) {
                    const field = form.elements.namedItem(name);
                    if (field) field.value = '';
                }
                HTMLFormElement.prototype.submit.call(form);
            }, refresh),
        ]);
    } else {
        const origin = new URL(page.url()).origin;
        [response] = await Promise.all([
            page.waitForResponse(res => new URL(res.url()).origin === origin
                && (res.request().method() === 'POST' ||
                    (res.request().isNavigationRequest() && res.request().frame() === page.mainFrame())), {timeout}),
            refresh.click(),
        ]);
    }
    if (!response || !response.ok()) throw new Error('Queue refresh failed; existing results were not captured.');
    console.log('[+] Refresh View response received; waiting for the updated queue grid');
    // Portal telemetry may keep connections open after the query has returned.
    // The refresh response is mandatory; global network idleness is best effort.
    await page.waitForNetworkIdle({idleTime: 750, timeout: Math.min(timeout, 10000)}).catch(() => {});
    await page.waitForFunction(grid => {
        const panel = document.querySelector(grid);
        return panel && [...panel.querySelectorAll('tr')].some(row => {
            const headers = [...row.cells].map(cell => cell.textContent.trim().replace(/\s+/g, ' '));
            return headers.includes('Arrival Time') && headers.includes('Task Status');
        });
    }, {timeout}, selector);
}

module.exports = {refreshQueue};
