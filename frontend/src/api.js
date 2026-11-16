let csrf = '';
const configured = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '');
const base = configured.endsWith('/api') ? configured : `${configured}/api`;

export function setCsrf(value) {
  csrf = value;
}

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData))
    headers.set('Content-Type', 'application/json');
  if (options.method && options.method !== 'GET') headers.set('X-CSRF-Token', csrf);
  const response = await fetch(`${base}${path}`, { credentials: 'include', ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : data.detail?.[0]?.msg;
    throw new Error(detail || `Request failed (${response.status}). Please try again.`);
  }
  return data;
}

export function fileUrl(reportId, page) {
  return `${base}/reports/${encodeURIComponent(reportId)}/file${page ? `#page=${page}` : ''}`;
}

export function briefUrl(analysisId) {
  return `${base}/analyses/${encodeURIComponent(analysisId)}/brief.pdf`;
}

export async function analyse(
  companyId,
  mode,
  onProgress = () => {},
  { refresh = false, signal } = {},
) {
  const result = await api('/analyses', {
    method: 'POST',
    body: JSON.stringify({ company_id: companyId, mode, refresh }),
    signal,
  });
  if (result.analysis_id) return api(`/analyses/${result.analysis_id}`, { signal });
  while (!signal?.aborted) {
    const job = await api(`/jobs/${result.job.id}`, { signal });
    onProgress(job);
    if (job.status === 'complete') return api(`/analyses/${job.analysis_id}`, { signal });
    if (job.status === 'failed') throw new Error(job.error || 'Analysis could not finish.');
    await new Promise((resolve, reject) => {
      const abort = () => {
        clearTimeout(timer);
        reject(new DOMException('Aborted', 'AbortError'));
      };
      const timer = setTimeout(() => {
        signal?.removeEventListener('abort', abort);
        resolve();
      }, 800);
      signal?.addEventListener('abort', abort, { once: true });
      if (signal?.aborted) abort();
    });
  }
  throw new DOMException('Aborted', 'AbortError');
}
