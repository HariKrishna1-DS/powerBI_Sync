// Validate the exact feed and artifacts before they can be uploaded to GitHub.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const yaml = require('js-yaml');

function verifyRelease(directory, version) {
  if (!/^\d+\.\d+\.\d+$/.test(version)) throw Error('A stable desktop version is required.');
  const installer = `Tv-Tracker-${version}-x64.exe`;
  const info = yaml.load(fs.readFileSync(path.join(directory, 'latest.yml'), 'utf8'));
  if (info?.version !== version || info.path !== installer || !Array.isArray(info.files) || info.files.length !== 1 || info.files[0].url !== installer) throw Error('Update manifest does not match the desktop version and installer.');
  const bytes = fs.readFileSync(path.join(directory, installer));
  const digest = crypto.createHash('sha512').update(bytes).digest('base64');
  if (!bytes.length || info.sha512 !== digest || info.files[0].sha512 !== digest || info.files[0].size !== bytes.length) throw Error('Installer size or SHA-512 does not match latest.yml.');
  for (const name of [`${installer}.blockmap`, `Tv-Tracker-${version}-x64.zip`, `Tv-Tracker-${version}-source.zip`]) {
    if (!fs.statSync(path.join(directory, name)).size) throw Error(`Empty release artifact: ${name}`);
  }
  return {version, installer, bytes: bytes.length, sha512Verified: true};
}
if (require.main === module) {
  const {version} = require('./package.json');
  console.log(JSON.stringify(verifyRelease(path.resolve(__dirname, '../release', version), version)));
}
module.exports = {verifyRelease};
