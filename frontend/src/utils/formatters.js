export function date(value, full = false) {
  if (!value) return 'Unknown';
  if (/^\d{4}(?:-00-00)?$/.test(value)) return value.slice(0, 4);
  if (/^\d{4}-\d{2}$/.test(value))
    return new Intl.DateTimeFormat('en-SG', { month: 'short', year: 'numeric' }).format(
      new Date(`${value}-01`),
    );
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Date unavailable';
  return new Intl.DateTimeFormat('en-SG', {
    dateStyle: 'medium',
    ...(full ? { timeStyle: 'short' } : {}),
  }).format(parsed);
}

export function relative(value) {
  if (!value) return 'Not analysed yet';
  const seconds = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 60) return 'Just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return date(value);
}
