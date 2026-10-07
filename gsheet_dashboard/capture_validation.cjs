function advertisedCount(text) {
  const value = String(text || '');
  const match = value.match(/\b(?:items?|records?)\s+[\d,]+\s+(?:to|-)\s+[\d,]+\s+of\s+([\d,]+)\b/i)
    || value.match(/\b([\d,]+)\s+(?:items?|records?)\b/i);
  return match ? Number(match[1].replaceAll(',', '')) : null;
}

function clientCount(evidence) {
  if (!evidence || !Number.isSafeInteger(evidence.total) || evidence.total < 1
      || !Number.isSafeInteger(evidence.pages) || evidence.pages < 1
      || !Number.isSafeInteger(evidence.index) || evidence.index < 0 || evidence.index >= evidence.pages) return null;
  return evidence.total;
}

function captureEvidence(rows, expected, pages) {
  if (!rows.length) throw Error('The queue is empty. Existing production was retained.');
  if (expected !== null && rows.length !== expected) throw Error(`Incomplete queue: expected ${expected} rows but received ${rows.length}. Existing production was retained.`);
  const keys = rows.map(row => String(row['Order Number'] || '').trim().toLowerCase());
  const identitiesPresent = keys.every(Boolean);
  if (identitiesPresent && new Set(keys).size !== keys.length) throw Error('Duplicate order numbers in the extracted queue. Existing production was retained.');
  return {kind: 'portal', complete: expected !== null && identitiesPresent, expected_rows: expected, actual_rows: rows.length, pages};
}
module.exports = {advertisedCount, clientCount, captureEvidence};
