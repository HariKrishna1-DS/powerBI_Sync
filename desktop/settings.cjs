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
  const {password, serviceAccount, uiPreferences, cloudSession, ...publicFields} = settings;
  return {...publicFields, passwordSet: !!password, serviceAccountEmail: serviceAccount ? JSON.parse(serviceAccount).client_email : '', googleConfigured: !!(serviceAccount && settings.spreadsheetId)};
}

function validateUiPreferences(input, previous = {theme:'system', orderViews:[]}) {
  const object = value => value && typeof value === 'object' && !Array.isArray(value);
  const text = (value, max) => typeof value === 'string' && value.length <= max;
  if (!object(input) || Buffer.byteLength(JSON.stringify(input)) > 131072 ||
      Object.keys(input).some(key => !['theme','orderViews','sidebarCollapsed','tableLayout'].includes(key))) throw Error('Invalid workspace preferences.');
  const next = {...previous};
  if ('tableLayout' in input) {
    const value = input.tableLayout;
    if (!object(value) || !['compact','all','custom'].includes(value.mode) ||
        !Array.isArray(value.hidden) || value.hidden.length > 100 || !value.hidden.every(key=>text(key,256)) ||
        !object(value.widths) || Object.keys(value.widths).length > 100 ||
        !Object.entries(value.widths).every(([key,width])=>text(key,256)&&Number.isInteger(width)&&width>=120&&width<=400) ||
        typeof value.pinIdentifier !== 'boolean' || typeof value.wrap !== 'boolean') throw Error('Invalid table layout.');
    next.tableLayout = JSON.parse(JSON.stringify(value));
  }
  if ('sidebarCollapsed' in input) {
    if (typeof input.sidebarCollapsed !== 'boolean') throw Error('Invalid sidebar preference.');
    next.sidebarCollapsed = input.sidebarCollapsed;
  }
  if ('theme' in input) {
    if (!['light','dark','system'].includes(input.theme)) throw Error('Invalid appearance.');
    next.theme = input.theme;
  }
  if ('orderViews' in input) {
    if (!Array.isArray(input.orderViews) || input.orderViews.length > 12) throw Error('Save at most 12 views.');
    const operators = ['none','contains','excludes','equals','blank','notblank','gt','lt','between'];
    for (const view of input.orderViews) {
      if (!object(view) || !text(view.name,50) || !view.name.trim() || !text(view.search,2048) ||
          !['all','attention'].includes(view.group) || !text(view.product,512) || !object(view.filters) ||
          Object.keys(view.filters).length > 100) throw Error('Invalid saved view.');
      for (const [column,filter] of Object.entries(view.filters)) {
        if (!text(column,256) || !object(filter) ||
            (filter.values != null && (!Array.isArray(filter.values) || filter.values.length > 2000 || !filter.values.every(v=>text(v,2048)))) ||
            (filter.operator != null && !operators.includes(filter.operator)) ||
            (filter.query != null && !text(filter.query,2048)) || (filter.end != null && !text(filter.end,2048))) throw Error('Invalid saved filter.');
      }
    }
    next.orderViews = JSON.parse(JSON.stringify(input.orderViews));
  }
  return next;
}

function createVault(file, safeStorage) {
  let recovery = null;
  function requireEncryption() {
    if (!safeStorage.isEncryptionAvailable()) throw Error('Windows credential encryption is unavailable. Sign into Windows and try again.');
  }
  function decode(buffer) {
        const value = JSON.parse(safeStorage.decryptString(buffer));
        if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('Invalid settings record.');
        const saved = {...DEFAULTS, ...value};
        for (const key of ['fullTrackerTitle', 'remainingTrackerTitle']) {
          if (saved[key] === `${DEFAULTS[key]}_-_September_2026`) saved[key] = DEFAULTS[key];
        }
        return saved;
  }
  function atomicWrite(target, bytes) {
    const temporary = `${target}.${process.pid}.tmp`;
    const fd = fs.openSync(temporary, 'w', 0o600);
    try { fs.writeFileSync(fd, bytes); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    fs.renameSync(temporary, target);
  }
  function backup() {
    if (!fs.existsSync(file)) return null;
    const directory = path.join(path.dirname(file), 'connection-backups', `${new Date().toISOString().replace(/[:.]/g, '-')}-${require('node:crypto').randomUUID()}`);
    fs.mkdirSync(directory, {recursive: true});
    for (const name of [path.basename(file), `${path.basename(file)}.bak`, 'Local State']) {
      const source = path.join(path.dirname(file), name);
      if (fs.existsSync(source)) fs.copyFileSync(source, path.join(directory, name), fs.constants.COPYFILE_EXCL);
    }
    return directory;
  }
  const vault = {
    status: () => recovery && {...recovery},
    backup,
    read() {
      if (!fs.existsSync(file)) return {...DEFAULTS};
      requireEncryption();
      try { return decode(fs.readFileSync(file)); }
      catch { throw Error('Saved connections could not be unlocked. Your original settings and workspace have been preserved.'); }
    },
    readRecoverably() {
      try {
        if (!fs.existsSync(file) && fs.existsSync(`${file}.bak`)) throw Error('Primary settings are missing.');
        return vault.read();
      }
      catch {
        try {
          requireEncryption();
          const previous = decode(fs.readFileSync(`${file}.bak`));
          backup();
          atomicWrite(file, fs.readFileSync(`${file}.bak`));
          recovery = {status: 'restored', message: 'Connections were restored from the last verified local backup. Check Connections & settings before your next capture.'};
          return previous;
        } catch {
          recovery = {status: 'locked', message: 'Saved connections could not be unlocked. Your captures and original settings are preserved. Reconnect in Connections & settings. Scheduled work is paused until connections are saved.'};
          return {...DEFAULTS};
        }
      }
    },
    write(settings, {replaceUnreadable = false} = {}) {
      if (recovery?.status === 'locked' && !replaceUnreadable) throw Error('Reconnect in Connections & settings before saving preferences. Your original settings are preserved.');
      requireEncryption();
      fs.mkdirSync(path.dirname(file), {recursive: true});
      const raw = JSON.stringify(settings);
      const encrypted = safeStorage.encryptString(raw);
      if (safeStorage.decryptString(encrypted) !== raw) throw Error('Windows could not verify the saved connections. Nothing was replaced.');
      if (recovery?.status === 'locked') backup();
      if (fs.existsSync(file) && recovery?.status !== 'locked') {
        const previous = fs.readFileSync(file);
        decode(previous);
        atomicWrite(`${file}.bak`, previous);
      }
      atomicWrite(file, encrypted);
      if (!fs.existsSync(`${file}.bak`) || recovery?.status === 'locked') atomicWrite(`${file}.bak`, encrypted);
      recovery = null;
    },
  };
  return vault;
}

function allowedExternal(value) {
  try { const url = new URL(value); return url.protocol === 'https:' && ['docs.google.com', 'console.cloud.google.com', 'tv.datatracetitle.com'].includes(url.hostname) && !url.username && !url.password; } catch { return false; }
}
module.exports = {DEFAULTS, validateSettings, validateServiceAccount, validateUiPreferences, publicSettings, createVault, allowedExternal};
