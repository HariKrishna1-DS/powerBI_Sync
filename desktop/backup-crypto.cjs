const crypto = require('node:crypto');
const {promisify} = require('node:util');
const scrypt = promisify(crypto.scrypt);
const MAGIC = Buffer.from('TVTRACKER-PORTABLE-1\n');
const LIMIT = 101 * 1024 * 1024;
function validatePassword(password) {
  if (typeof password !== 'string' || password.length < 12 || password.length > 1024) throw Error('Use a backup password of 12–1024 characters. Keep it separately; it cannot be recovered.');
}
async function keyFor(password, salt) {
  validatePassword(password);
  return scrypt(password, salt, 32, {N: 131072, r: 8, p: 1, maxmem: 256 * 1024 * 1024});
}
async function encryptBackup(raw, password) {
  if (!Buffer.isBuffer(raw) || raw.length > LIMIT) throw Error('Backup exceeds the supported size.');
  const salt = crypto.randomBytes(16), nonce = crypto.randomBytes(12);
  const header = Buffer.concat([MAGIC, salt, nonce]);
  const key = await keyFor(password, salt);
  try {
    const cipher = crypto.createCipheriv('aes-256-gcm', key, nonce);
    cipher.setAAD(header);
    const data = Buffer.concat([cipher.update(raw), cipher.final()]);
    return Buffer.concat([header, cipher.getAuthTag(), data]);
  } finally { key.fill(0); }
}
async function decryptBackup(raw, password) {
  if (!Buffer.isBuffer(raw) || raw.length > LIMIT) throw Error('Backup exceeds the supported size.');
  if (!raw.subarray(0, MAGIC.length).equals(MAGIC)) return raw; // Legacy ZIP / Windows-account backup: engine validates.
  const offset = MAGIC.length;
  if (raw.length < offset + 44) throw Error('The encrypted backup is incomplete.');
  const key = await keyFor(password, raw.subarray(offset, offset + 16));
  try {
    const decipher = crypto.createDecipheriv('aes-256-gcm', key, raw.subarray(offset + 16, offset + 28));
    decipher.setAAD(raw.subarray(0, offset + 28));
    decipher.setAuthTag(raw.subarray(offset + 28, offset + 44));
    return Buffer.concat([decipher.update(raw.subarray(offset + 44)), decipher.final()]);
  } catch { throw Error('Incorrect backup password or damaged backup. Your workspace was not changed.'); }
  finally { key.fill(0); }
}
module.exports = {encryptBackup, decryptBackup, validatePassword};
