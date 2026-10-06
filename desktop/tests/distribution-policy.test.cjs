const {test} = require('node:test');
const assert = require('node:assert/strict');
const {validateDistribution} = require('../distribution-policy.cjs');
const policy = require('../distribution-policy.json');
test('owner distribution policy is version-independent and never accepts invalid signatures', () => {
  assert.match(validateDistribution(policy, 'NotSigned', policy.repository), /unsigned/);
  assert.match(validateDistribution(policy, 'Valid', policy.repository), /digitally signed/);
  for (const status of ['HashMismatch', 'NotTrusted', 'UnknownError', 'NotSupportedFileFormat', '', undefined]) {
    assert.throws(() => validateDistribution(policy, status, policy.repository), /rejected/);
  }
  assert.throws(() => validateDistribution({...policy, mode: 'signed-only'}, 'NotSigned', policy.repository));
  assert.throws(() => validateDistribution(policy, 'Valid', 'other/repo'));
  assert.throws(() => validateDistribution({...policy, mode: 'typo'}, 'Valid', policy.repository));
});
