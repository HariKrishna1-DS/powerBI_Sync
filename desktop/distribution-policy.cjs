// Build/publishing policy only. Never disables updater checksum verification.
function validateDistribution(policy, signatureStatus, repository) {
  if (!policy || !['signed-only', 'unsigned-or-valid'].includes(policy.mode) ||
      repository !== policy.repository || repository !== 'HariKrishna1-DS/powerBI_Sync') {
    throw Error('Unrecognized release distribution policy or repository.');
  }
  if (signatureStatus === 'Valid') return 'The Windows installer is digitally signed.';
  if (signatureStatus === 'NotSigned' && policy.mode === 'unsigned-or-valid') {
    return 'The Windows installer is unsigned under the owner-selected no-purchase distribution policy. Windows may show an unknown-publisher warning. SHA-512 verifies download integrity; it does not establish a verified publisher identity.';
  }
  throw Error(`Installer signature rejected: ${signatureStatus}. Invalid signatures are never permitted.`);
}
if (require.main === module) {
  console.log(validateDistribution(require('./distribution-policy.json'), process.argv[2], process.argv[3]));
}
module.exports = {validateDistribution};
