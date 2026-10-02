const fs = require('node:fs');
const path = require('node:path');

const DEFAULTS = Object.freeze({
  spreadsheetId: '', queueUrl: 'https://tv.datatracetitle.com/Queues.aspx?qid=23656',
  fullTrackerTitle: 'TV_Search_Production_Report_Full_Search',
  remainingTrackerTitle: 'TV_Search_Production_Report_C-O_and_Update',
  username: '', password: '', serviceAccount: '', browserPath: '', closeToTray: true, startAtLogin: false,
});

function validateSettings(input, previous = DEFAULTS) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw Error('Settings must be an object.');
  const next = {...previous};
  for (const key of ['spreadsheetId', 'queueUrl', 'fullTrackerTitle', 'remainingTrackerTitle', 'username', 'browserPath']) {
    if (key in input) {
      if (typeof input[key] !== 'string' || input[key].length > 2048) throw Error(`Invalid ${key}.`);
      next[key] = input[key].trim();
    }
  }
  const match = next.spreadsheetId.match(/^https:\/\/docs\.google\.com\/spreadsheets\/d\/([a-zA-Z0-9_-]+)/);
  if (match) next.spreadsheetId = match[1];
  if (next.spreadsheetId && !/^[a-zA-Z0-9_-]{20,150}$/.test(next.spreadsheetId)) throw Error('Enter a valid Google Sheets URL or spreadsheet ID.');
  let url;
  try { url = new URL(next.queueUrl); } catch { throw Error('Enter a valid TitleVision queue URL.'); }
  if (url.protocol !== 'https:' || url.hostname !== 'tv.datatracetitle.com' || url.username || url.password) throw Error('Use an HTTPS queue URL on tv.datatracetitle.com.');
  for (const key of ['fullTrackerTitle', 'remainingTrackerTitle']) {
    if (!next[key] || next[key].length > 100 || /[\[\]:*?\/\\]/.test(next[key])) throw Error('Tracker names must be valid Google Sheets tab names, up to 100 characters.');
  }
  if (next.fullTrackerTitle === next.remainingTrackerTitle) throw Error('The two production tracker names must be different.');
  if ('password' in input && input.password !== '') {
    if (typeof input.password !== 'string' || input.password.length > 4096) throw Error('Invalid password.');
    next.password = input.password;
  }
  if (input.clearPassword === true) next.password = '';
  for (const key of ['closeToTray', 'startAtLogin']) {
    if (key in input) {
      if (typeof input[key] !== 'boolean') throw Error(`Invalid ${key}.`);
      next[key] = input[key];
    }
  }
  if (next.browserPath && (!path.isAbsolute(next.browserPath) || !fs.existsSync(next.browserPath) || !/\.(exe)$/i.test(next.browserPath))) throw Error('Choose an installed Edge or Chrome executable.');
  return next;
}

function validateServiceAccount(raw) {
  if (typeof raw !== 'string' || Buffer.byteLength(raw) > 65536) throw Error('Service-account file is invalid or too large.');
  let data;
  try { data = JSON.parse(raw); } catch { throw Error('The selected file is not valid JSON.'); }
  if (data.type !== 'service_account' || !/^[^\s@]+@[^\s@]+\.gserviceaccount\.com$/.test(data.client_email || '') || !data.private_key?.startsWith('-----BEGIN PRIVATE KEY-----') || !data.project_id) throw Error('Choose a Google service-account JSON key file.');
  // Only permit Google's token endpoint; a supplied key file cannot redirect credentials.
  if (data.token_uri !== 'https://oauth2.googleapis.com/token') throw Error('The key file must use Google’s official token endpoint.');
  return JSON.stringify(data);
}

function publicSettings(settings) {
  const {password, serviceAccount, ...publicFields} = settings;
  return {...publicFields, passwordSet: !!password, serviceAccountEmail: serviceAccount ? JSON.parse(serviceAccount).client_email : '', googleConfigured: !!(serviceAccount && settings.spreadsheetId)};
}

function createVault(file, safeStorage) {
  function requireEncryption() {
    if (!safeStorage.isEncryptionAvailable()) throw Error('Windows credential encryption is unavailable. Sign into Windows and try again.');
  }
  return {
    read() {
      if (!fs.existsSync(file)) return {...DEFAULTS};
      requireEncryption();
      try {
        const saved = {...DEFAULTS, ...JSON.parse(safeStorage.decryptString(fs.readFileSync(file)))};
        for (const key of ['fullTrackerTitle', 'remainingTrackerTitle']) {
          if (saved[key] === `${DEFAULTS[key]}_-_September_2026`) saved[key] = DEFAULTS[key];
        }
        return saved;
      }
      catch { throw Error('Saved settings could not be decrypted for this Windows account. Restore your original account or move settings.vault aside to configure a new connection.'); }
    },
    write(settings) {
      requireEncryption();
      fs.mkdirSync(path.dirname(file), {recursive: true});
      const temporary = `${file}.tmp`;
      fs.writeFileSync(temporary, safeStorage.encryptString(JSON.stringify(settings)), {mode: 0o600});
      fs.renameSync(temporary, file);
    },
  };
}

function allowedExternal(value) {
  try { const url = new URL(value); return url.protocol === 'https:' && ['docs.google.com', 'console.cloud.google.com', 'tv.datatracetitle.com'].includes(url.hostname) && !url.username && !url.password; } catch { return false; }
}
module.exports = {DEFAULTS, validateSettings, validateServiceAccount, publicSettings, createVault, allowedExternal};
