import type { ErrorEnvelope, ProjectSummary, Revision, RunRecord, StageEvent } from '@/domain/types'
import { ApiError, type ServiceHealth, type UnlockApi } from './client'

/**
 * FastAPI adapter for the endpoints in PRD §20. Not exercised in this build:
 * set VITE_UNLOCK_API to the coordinator origin to enable it.
 */
export function createHttpApi(source: string | (() => string), auth: () => Record<string, string> = () => ({})): UnlockApi {
  const base = () => typeof source === 'string' ? source : source()
  const url = (p: string) => `${base().replace(/\/$/, '')}${p}`

  async function call<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(url(path), {
      ...init,
      headers: { ...auth(), Accept: 'application/json', ...(init?.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...init?.headers },
    })
    if (!res.ok) {
      const envelope = (await res.json().catch(() => null)) as ErrorEnvelope | null
      throw new ApiError(
        envelope ?? { error_code: 'NOT_FOUND', message: `${res.status} ${res.statusText}`, retryable: res.status >= 500, field_errors: [], evidence_ids: [], run_id: null },
        res.status,
      )
    }
    return res.json() as Promise<T>
  }

  const idem = () => crypto.randomUUID()

  return {
    mode: 'http',
    get origin() { return base().replace(/\/$/, '') },
    artifactHeaders: auth,
    health: async () => (await call<{ provider: ServiceHealth }>('/health')).provider,
    listProjects: () => call<ProjectSummary[]>('/v1/projects'),
    latestRevisionId: async (projectId) => {
      const p = await call<{ revisions: Array<{ id: string }> }>(`/v1/projects/${encodeURIComponent(projectId)}`)
      const revision = p.revisions[p.revisions.length - 1]
      if (!revision) throw new Error('The assembly is still importing. Return to Projects and wait for Ready.')
      return revision.id
    },
    getRevision: (id) => call<Revision>(`/v1/revisions/${encodeURIComponent(id)}`),
    importPackage: (files) => {
      const body = new FormData()
      files.forEach((f) => body.append('package', f, f.name))
      return call('/v1/projects/default/imports', { method: 'POST', body, headers: { 'Idempotency-Key': idem() } })
    },
    startRun: (revisionId, body) =>
      call(`/v1/revisions/${encodeURIComponent(revisionId)}/runs`, { method: 'POST', body: JSON.stringify(body), headers: { 'Idempotency-Key': idem() } }),
    requestRedesign: (runId) => call(`/v1/runs/${encodeURIComponent(runId)}/redesign`, { method: 'POST', headers: { 'Idempotency-Key': idem() } }),
    streamEvents: (jobId, onEvent, signal) =>
      new Promise<void>((resolve, reject) => {
        if (signal.aborted) { resolve(); return }
        const source = new EventSource(url(`/v1/jobs/${encodeURIComponent(jobId)}/events`))
        const cleanup = () => { source.close(); signal.removeEventListener('abort', abort) }
        const abort = () => { cleanup(); resolve() }
        signal.addEventListener('abort', abort, { once: true })
        source.onmessage = (m) => {
          try {
            const e = JSON.parse(m.data) as StageEvent & { terminal?: boolean; job_state?: string; error?: ErrorEnvelope }
            onEvent(e)
            if (e.terminal) {
              cleanup()
              if (e.job_state === 'failed' || e.job_state === 'interrupted' || e.job_state === 'cancelled') reject(new Error(e.error?.message ?? `Job ${e.job_state}`))
              else resolve()
            }
          } catch (e) { cleanup(); reject(e) }
        }
        // EventSource reconnects transient interruptions with Last-Event-ID.
        // A CLOSED stream cannot reconnect; keep all existing engineering evidence.
        source.onerror = () => {
          if (source.readyState === EventSource.CLOSED) { cleanup(); reject(new Error('Event stream closed. Reopen the run to inspect its persisted state.')) }
        }
      }),
    getRun: (id) => call<RunRecord>(`/v1/runs/${encodeURIComponent(id)}`),
    cancelJob: async (id) => { await call(`/v1/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST', headers: { 'Idempotency-Key': idem() } }) },
    artifactUrl: (id) => url(`/v1/artifacts/${encodeURIComponent(id)}`),
    decide: (candidateId, decision, input_hash) =>
      call(`/v1/candidates/${encodeURIComponent(candidateId)}/decision`, { method: 'POST', body: JSON.stringify({ decision, input_hash }) }),
    requestExport: (candidateId) =>
      call(`/v1/candidates/${encodeURIComponent(candidateId)}/exports`, { method: 'POST', headers: { 'Idempotency-Key': idem() } }),
  }
}
