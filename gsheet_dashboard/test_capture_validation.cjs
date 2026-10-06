const {test} = require('node:test');
const assert = require('node:assert/strict');
const {advertisedCount, captureEvidence} = require('./capture_validation.cjs');
test('partial, changing and duplicate queue evidence cannot establish completeness', () => {
  assert.equal(advertisedCount('1,234 items in 42 pages'), 1234);
  assert.equal(advertisedCount('Page 1'), null);
  const rows = [{'Order Number': '001'}, {'Order Number': '002'}];
  assert.equal(captureEvidence(rows, 2, 2).complete, true);
  assert.equal(captureEvidence(rows, null, 2).complete, false);
  assert.throws(() => captureEvidence(rows, 3, 2), /Incomplete queue/);
  assert.throws(() => captureEvidence([rows[0], rows[0]], 2, 1), /Duplicate/);
  assert.equal(captureEvidence([{OPON: '001'}], 1, 1).complete, false);
});
