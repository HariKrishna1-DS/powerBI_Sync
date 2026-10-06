const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {writeVerifiedFile} = require('../verified-file.cjs');

test('failed backup flush, readback or rename preserves the previous export and removes temporary files', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'tv-backup-export-'));
  const target = path.join(directory, 'backup.zip');
  try {
    fs.writeFileSync(target, 'previous');
    for (const io of [
      {...fs, fsyncSync() { throw Error('disk full'); }},
      {...fs, readFileSync() { return Buffer.from('truncated'); }},
      {...fs, renameSync() { throw Error('file locked'); }},
    ]) {
      assert.throws(() => writeVerifiedFile(target, Buffer.from('replacement'), io));
      assert.equal(fs.readFileSync(target, 'utf8'), 'previous');
      assert.deepEqual(fs.readdirSync(directory), ['backup.zip']);
    }
    writeVerifiedFile(target, Buffer.from('replacement'));
    assert.equal(fs.readFileSync(target, 'utf8'), 'replacement');
    assert.deepEqual(fs.readdirSync(directory), ['backup.zip']);
  } finally { fs.rmSync(directory, {recursive: true}); }
});
