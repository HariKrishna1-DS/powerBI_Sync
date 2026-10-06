const {test} = require('node:test');
const assert = require('node:assert/strict');
const {encryptBackup, decryptBackup} = require('../backup-crypto.cjs');
test('portable backup restores with password and rejects tampering/wrong password', async () => {
  const data = Buffer.from('PK synthetic confidential production archive');
  const password = 'Fixture-only password 2026!';
  const encrypted = await encryptBackup(data, password);
  assert.ok(!encrypted.includes(data));
  assert.deepEqual(await decryptBackup(encrypted, password), data);
  await assert.rejects(decryptBackup(encrypted, 'wrong fixture password'), /Incorrect backup password/);
  const damaged = Buffer.from(encrypted); damaged[damaged.length - 1] ^= 1;
  await assert.rejects(decryptBackup(damaged, password), /damaged backup/);
  const other = await encryptBackup(data, password);
  assert.notDeepEqual(other, encrypted);
  await assert.rejects(encryptBackup(data, 'short'), /12/);
  assert.deepEqual(await decryptBackup(data, ''), data);
});
