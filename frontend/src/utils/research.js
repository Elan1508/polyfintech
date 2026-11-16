export function companyInitials(name = '') {
  const words = name.split(/\s+/).filter((word) => /^\p{L}/u.test(word));
  return (
    words
      .slice(0, 2)
      .map((word) => [...word][0])
      .join('')
      .toLocaleUpperCase() || 'CO'
  );
}
export function scoreTone(metric, value) {
  if (value == null) return 'neutral';
  if (metric === 'risk') return value >= 45 ? 'danger' : 'warn';
  return value >= 65 ? 'accent' : value < 40 ? 'danger' : 'warn';
}
export function previousChanges(rows = []) {
  const current = rows.at(-1),
    previous = rows.at(-2);
  if (!previous || current.scoring_version !== previous.scoring_version) return {};
  return Object.fromEntries(
    Object.keys(current.scores).flatMap((key) => {
      const a = current.scores[key].score,
        b = previous.scores[key].score;
      return a == null || b == null ? [] : [[key, a - b]];
    }),
  );
}
export function chartPoints(
  rows = [],
  metric = 'momentum',
  version = rows.at(-1)?.scoring_version,
) {
  return rows.map((row) => ({
    id: row.id,
    timestamp: Date.parse(row.created_at),
    created_at: row.created_at,
    value: row.scoring_version === version ? (row.scores[metric]?.score ?? null) : null,
  }));
}
export function zeroRiskFlags(analysis) {
  return (
    analysis?.scores.risk.score == null &&
    analysis?.risk_flag_count === 0 &&
    analysis?.coverage.source_count > 0
  );
}
