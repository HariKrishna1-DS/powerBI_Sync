const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {verifyRelease} = require('../verify-release.cjs');

test('release gate rejects mismatched versions, modified installers and incomplete uploads', () => {
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'tv-release-verify-'));
  const name='Tv-Tracker-2.4.1-x64.exe';
  const bytes=Buffer.from('synthetic installer fixture');
  const sha512=crypto.createHash('sha512').update(bytes).digest('base64');
  const info={version:'2.4.1',path:name,sha512,files:[{url:name,sha512,size:bytes.length}]};
  const manifest=value=>fs.writeFileSync(path.join(dir,'latest.yml'),JSON.stringify(value));
  try {
    fs.writeFileSync(path.join(dir,name),bytes);
    for(const file of [`${name}.blockmap`,'Tv-Tracker-2.4.1-x64.zip','Tv-Tracker-2.4.1-source.zip'])fs.writeFileSync(path.join(dir,file),'fixture');
    manifest(info);assert.equal(verifyRelease(dir,'2.4.1').sha512Verified,true);
    manifest({...info,version:'2.4.0'});assert.throws(()=>verifyRelease(dir,'2.4.1'),/manifest/);
    manifest(info);fs.writeFileSync(path.join(dir,name),'tampered');assert.throws(()=>verifyRelease(dir,'2.4.1'),/SHA-512/);
    fs.writeFileSync(path.join(dir,name),bytes);fs.unlinkSync(path.join(dir,`${name}.blockmap`));assert.throws(()=>verifyRelease(dir,'2.4.1'));
  } finally {fs.rmSync(dir,{recursive:true});}
});
