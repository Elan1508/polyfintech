import test from 'node:test';
import assert from 'node:assert/strict';
import {
  chartPoints,
  companyInitials,
  previousChanges,
  zeroRiskFlags,
} from '../src/utils/research.js';

test('company monograms use names, including Unicode, rather than numeric tickers', () => {
  assert.equal(companyInitials('DBS Group Holdings'), 'DG');
  assert.equal(companyInitials('Oversea-Chinese Banking Corporation'), 'OB');
  assert.equal(companyInitials('123 Example Company'), 'EC');
  assert.equal(companyInitials('Énergie Générale'), 'ÉG');
  assert.equal(companyInitials(''), 'CO');
});
const snapshot = (id, created_at, score, version = 'evidence-2.1') => ({
  id,
  created_at,
  scoring_version: version,
  scores: { momentum: { score }, risk: { score: null } },
});
test('trends preserve actual date spacing and gaps rather than inventing observations', () => {
  const rows = [
    snapshot('a', '2026-10-01T00:00:00Z', 40),
    snapshot('b', '2026-10-02T00:00:00Z', null),
    snapshot('c', '2026-10-12T00:00:00Z', 60),
  ];
  const points = chartPoints(rows);
  assert.equal(points.length, 3);
  assert.equal(points[1].value, null);
  assert.equal(
    points[2].timestamp - points[1].timestamp,
    10 * (points[1].timestamp - points[0].timestamp),
  );
  assert.equal(
    chartPoints([snapshot('old', '2026-10-01T00:00:00Z', 90, 'old'), rows[2]])[0].value,
    null,
  );
});
test('score changes exclude different methods and unavailable scores', () => {
  const first = snapshot('a', '2026-10-01T00:00:00Z', 40);
  assert.deepEqual(previousChanges([first, snapshot('b', '2026-10-02T00:00:00Z', 52)]), {
    momentum: 12,
  });
  assert.deepEqual(
    previousChanges([first, snapshot('b', '2026-10-02T00:00:00Z', 52, 'other')]),
    {},
  );
  assert.deepEqual(previousChanges([first]), {});
});
test('zero flags is distinct from a zero risk score and unavailable research', () => {
  const item = {
    scores: { risk: { score: null } },
    risk_flag_count: 0,
    coverage: { source_count: 3 },
  };
  assert.equal(zeroRiskFlags(item), true);
  assert.equal(zeroRiskFlags({ ...item, coverage: { source_count: 0 } }), false);
  assert.equal(zeroRiskFlags({ ...item, risk_flag_count: undefined }), false);
  assert.equal(zeroRiskFlags({ ...item, scores: { risk: { score: 0 } } }), false);
});
