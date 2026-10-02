const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {DEFAULTS, validateSettings, validateServiceAccount, publicSettings, createVault, allowedExternal} = require('../settings.cjs');

test('spreadsheet URLs are normalized and empty passwords preserve saved credentials', () => {
  const value = validateSettings({spreadsheetId: 'https://docs.google.com/spreadsheets/d/1234567890123456789012345/edit', password: ''}, {...DEFAULTS, password: 'saved-value'});
  assert.equal(value.spreadsheetId, '1234567890123456789012345');
  assert.equal(value.password, 'saved-value');
  assert.equal(validateSettings({clearPassword: true}, value).password, '');
});
test('settings reject credential destinations and malformed tracker configuration', () => {
  for (const queueUrl of ['http://tv.datatracetitle.com', 'https://tv.datatracetitle.com.evil.example', 'https://user:secret@tv.datatracetitle.com', 'javascript:alert(1)']) assert.throws(() => validateSettings({queueUrl}));
  assert.throws(() => validateSettings({fullTrackerTitle: '../invalid'}));
  assert.throws(() => validateSettings({fullTrackerTitle: 'Same', remainingTrackerTitle: 'Same'}));
  assert.throws(() => validateSettings({closeToTray: 'false'}));
});
test('service-account imports reject alternate token servers and public settings omit secrets', () => {
  const key = {type: 'service_account', project_id: 'test', client_email: 'test@test.iam.gserviceaccount.com', private_key: '-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----', token_uri: 'https://oauth2.googleapis.com/token'};
  const account = validateServiceAccount(JSON.stringify(key));
  const state = publicSettings({...DEFAULTS, password: 'test-password', serviceAccount: account});
  assert.equal(state.passwordSet, true);
  assert.equal(state.serviceAccountEmail, key.client_email);
  assert.equal('password' in state, false);
  assert.equal('serviceAccount' in state, false);
  assert.throws(() => validateServiceAccount(JSON.stringify({...key, token_uri: 'https://evil.example/token'})));
  assert.throws(() => validateServiceAccount('{not-json}'));
});
test('vault uses encryption, round-trips, and fails closed on a corrupt file', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'datatrace-vault-'));
  const file = path.join(directory, 'settings.vault');
  const key = crypto.randomBytes(32);
  const safeStorage = {
    isEncryptionAvailable: () => true,
    encryptString(value) { const iv = crypto.randomBytes(12); const cipher = crypto.createCipheriv('aes-256-gcm', key, iv); const encrypted = Buffer.concat([cipher.update(value), cipher.final()]); return Buffer.concat([iv, cipher.getAuthTag(), encrypted]); },
    decryptString(value) { const cipher = crypto.createDecipheriv('aes-256-gcm', key, value.subarray(0, 12)); cipher.setAuthTag(value.subarray(12, 28)); return Buffer.concat([cipher.update(value.subarray(28)), cipher.final()]).toString(); },
  };
  try {
    const vault = createVault(file, safeStorage);
    vault.write({...DEFAULTS, password: 'do-not-store-plaintext'});
    assert.equal(fs.readFileSync(file).includes('do-not-store-plaintext'), false);
    assert.equal(vault.read().password, 'do-not-store-plaintext');
    fs.writeFileSync(file, 'damaged');
    assert.throws(() => vault.read(), /could not be decrypted/);
    safeStorage.isEncryptionAvailable = () => false;
    assert.throws(() => vault.write(DEFAULTS), /unavailable/);
  } finally { fs.rmSync(directory, {recursive: true}); }
});
test('external navigation allows exact service hosts and HTTPS only', () => {
  assert.equal(allowedExternal('https://docs.google.com/spreadsheets/d/example'), true);
  for (const url of ['file:///C:/Windows', 'https://docs.google.com.evil.test', 'http://docs.google.com', 'https://user:pass@docs.google.com', 'javascript:alert(1)']) assert.equal(allowedExternal(url), false);
});
