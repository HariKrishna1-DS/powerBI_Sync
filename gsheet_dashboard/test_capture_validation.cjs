const {test} = require('node:test');
const assert = require('node:assert/strict');
const {advertisedCount, clientCount, captureEvidence} = require('./capture_validation.cjs');
test('partial, changing and duplicate queue evidence cannot establish completeness', () => {
  assert.equal(advertisedCount('1,234 items in 42 pages'), 1234);
  assert.equal(advertisedCount('Page 1'), null);
  assert.equal(advertisedCount('Page 1 of 3, items 1 to 10 of 25.'), 25);
  assert.equal(clientCount({total:477,pages:1,index:0}), 477);
  for (const value of [null, {}, {total:0,pages:1,index:0}, {total:477,pages:1,index:1}, {total:'477',pages:1,index:0}]) assert.equal(clientCount(value), null);
  const rows = [{'Order Number': '001'}, {'Order Number': '002'}];
  assert.equal(captureEvidence(rows, 2, 2).complete, true);
  assert.equal(captureEvidence(rows, null, 2).complete, false);
  assert.throws(() => captureEvidence(rows, 3, 2), /Incomplete queue/);
  assert.throws(() => captureEvidence([rows[0], rows[0]], 2, 1), /Duplicate/);
  assert.equal(captureEvidence([{OPON: '001'}], 1, 1).complete, false);
});
