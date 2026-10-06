const {test} = require('node:test');
const assert = require('node:assert/strict');
const {redact} = require('../redaction.cjs');
test('standalone and JSON-escaped account secrets are removed from diagnostic errors', () => {
  const privateKey = '-----BEGIN PRIVATE KEY-----\nfixture-secret\n-----END PRIVATE KEY-----';
  const account = JSON.stringify({private_key: privateKey, private_key_id: 'fixture-key-id'});
  for (const message of [privateKey, JSON.stringify(privateKey), account, 'password fixture-key-id']) {
    const result = redact(message, [account, 'password']);
    assert.ok(!result.includes('fixture-secret'));
    assert.ok(!result.includes('fixture-key-id'));
    assert.ok(!result.includes('password'));
  }
});
