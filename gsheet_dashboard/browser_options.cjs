function browserOptions(env = process.env, platform = process.platform) {
    const args = ['--start-maximized'];
    if (platform === 'linux') args.push('--disable-dev-shm-usage');
    // Opt in only for container hosts that cannot provide Chromium's sandbox.
    if (platform === 'linux' && env.DATATRACE_CHROME_NO_SANDBOX === 'true') {
        args.push('--no-sandbox', '--disable-setuid-sandbox');
    }
    return {
        headless: env.DATATRACE_HEADLESS !== 'false',
        defaultViewport: null,
        timeout: Number(env.DATATRACE_TIMEOUT_MS || 120000),
        ...(env.PUPPETEER_EXECUTABLE_PATH ? {executablePath: env.PUPPETEER_EXECUTABLE_PATH} : {}),
        args,
    };
}

module.exports = {browserOptions};
