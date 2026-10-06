const fs = require('node:fs');
const crypto = require('node:crypto');

function writeVerifiedFile(target, bytes, io = fs) {
  const temporary = `${target}.${crypto.randomUUID()}.tmp`;
  const digest = value => crypto.createHash('sha256').update(value).digest('hex');
  let descriptor;
  try {
    descriptor = io.openSync(temporary, 'wx', 0o600);
    io.writeFileSync(descriptor, bytes);
    io.fsyncSync(descriptor);
    io.closeSync(descriptor);
    descriptor = undefined;
    if (digest(io.readFileSync(temporary)) !== digest(bytes)) throw Error('Backup readback verification failed. The previous file was retained.');
    io.renameSync(temporary, target);
  } finally {
    if (descriptor !== undefined) io.closeSync(descriptor);
    if (io.existsSync(temporary)) io.unlinkSync(temporary);
  }
}
module.exports = {writeVerifiedFile};
