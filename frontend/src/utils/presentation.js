import { fileUrl } from '../api';

export const metricNames = {
  momentum: 'ESG report language',
  risk: 'ESG risk signals',
  digital: 'Digital responsibility signals',
};

const labels = {
  'Improving signals': 'Positive report language',
  'Mixed signals': 'Mixed report language',
  'Declining signals': 'Adverse report language',
  'Adverse signals': 'Adverse report language',
  'Improvement candidate': 'Positive language to investigate',
  Unassessed: 'More information needed',
  'Insufficient evidence': 'More information needed',
  'Context only': 'Background information',
  Available: 'Research available',
  'Moderate coverage': 'Research available',
  'Limited evidence': 'Limited public information',
  'Demo evidence': 'Demo data',
  'No flags in collected evidence': 'No risk signals in these sources',
  'Elevated flags': 'Elevated risk signals',
  'Flags detected': 'Risk signals to review',
  'Responsible technology': 'Digital responsibility',
  'First observation recorded.': 'Your first analysis is ready.',
  'Your first analysis has been saved.': 'Your first analysis is ready.',
};
export function friendlyLabel(value) {
  return labels[value] || value;
}
export function sourceType(source) {
  if (source.kind === 'news' && source.self_reported) return 'Company update';
  if (source.kind === 'disclosure' && !source.page) return 'Company publication';
  return (
    {
      news: 'News coverage',
      disclosure: 'Company report',
      report: 'Uploaded report',
      demo: 'Demo data',
    }[source.kind] || 'Company information'
  );
}
export function sourceHref(source) {
  if (source.report_id) return fileUrl(source.report_id, source.page);
  return source.url ? source.url.split('#')[0] + (source.page ? `#page=${source.page}` : '') : '';
}
const countries = new Intl.DisplayNames(['en'], { type: 'region' });
export function countryName(value) {
  if (value === 'US filing') return 'US-listed';
  try {
    return /^[A-Z]{2}$/.test(value) ? countries.of(value) : value;
  } catch {
    return value;
  }
}
