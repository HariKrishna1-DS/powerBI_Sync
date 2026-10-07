const fs = require('fs');
const path = require('path');

function browserOptions(env = process.env, platform = process.platform) {
    const args = ['--start-maximized'];
    if (platform === 'linux') args.push('--disable-dev-shm-usage');
    // Opt in only for container hosts that cannot provide Chromium's sandbox.
    if (platform === 'linux' && env.DATATRACE_CHROME_NO_SANDBOX === 'true') {
        args.push('--no-sandbox', '--disable-setuid-sandbox');
    }
    let executablePath = env.PUPPETEER_EXECUTABLE_PATH;
    if (!executablePath && platform === 'win32') {
        executablePath = [env.PROGRAMFILES, env['PROGRAMFILES(X86)'], env.LOCALAPPDATA]
            .filter(Boolean).flatMap(root => [
                path.join(root, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
                path.join(root, 'Google', 'Chrome', 'Application', 'chrome.exe'),
            ]).find(candidate => fs.existsSync(candidate));
    }
    return {
        headless: env.DATATRACE_HEADLESS !== 'false',
        defaultViewport: null,
        timeout: Number(env.DATATRACE_TIMEOUT_MS || 120000),
        ...(executablePath ? {executablePath} : {}),
        args,
    };
}

module.exports = {browserOptions};
