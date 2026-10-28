import type { ErrorEnvelope, ProjectSummary, Revision, RunRecord, StageEvent } from '@/domain/types'
import { ApiError, type UnlockApi } from './client'

/**
 * FastAPI adapter for the endpoints in PRD §20. Not exercised in this build:
 * set VITE_UNLOCK_API to the coordinator origin to enable it.
 */
export function createHttpApi(base: string): UnlockApi {
  const url = (p: string) => `${base.replace(/\/$/, '')}${p}`

  async function call<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(url(path), {
      ...init,
      headers: { Accept: 'application/json', ...(init?.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...init?.headers },
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
    listProjects: () => call<ProjectSummary[]>('/v1/projects'),
    latestRevisionId: async (projectId) => {
      const p = await call<{ revisions: Array<{ id: string }> }>(`/v1/projects/${encodeURIComponent(projectId)}`)
      return p.revisions[p.revisions.length - 1].id
    },
    getRevision: (id) => call<Revision>(`/v1/revisions/${encodeURIComponent(id)}`),
    importPackage: (files) => {
      const body = new FormData()
      files.forEach((f) => body.append('package', f, f.name))
      return call('/v1/projects/default/imports', { method: 'POST', body, headers: { 'Idempotency-Key': idem() } })
    },
    startRun: (revisionId, body) =>
      call(`/v1/revisions/${encodeURIComponent(revisionId)}/runs`, { method: 'POST', body: JSON.stringify(body) }),
    requestRedesign: (runId) => call(`/v1/runs/${encodeURIComponent(runId)}/redesign`, { method: 'POST', headers: { 'Idempotency-Key': idem() } }),
    streamEvents: (jobId, onEvent, signal) =>
      new Promise<void>((resolve, reject) => {
        const source = new EventSource(url(`/v1/jobs/${encodeURIComponent(jobId)}/events`))
        const close = () => {
          source.close()
          resolve()
        }
        signal.addEventListener('abort', close, { once: true })
        source.onmessage = (m) => {
          const e = JSON.parse(m.data) as StageEvent & { terminal?: boolean }
          onEvent(e)
          if (e.terminal) close()
        }
        source.onerror = () => {
          source.close()
          reject(new Error('Event stream interrupted. The run continues on the server; reconnect to resume.'))
        }
      }),
    getRun: (id) => call<RunRecord>(`/v1/runs/${encodeURIComponent(id)}`),
    decide: (candidateId, decision, input_hash) =>
      call(`/v1/candidates/${encodeURIComponent(candidateId)}/decision`, { method: 'POST', body: JSON.stringify({ decision, input_hash }) }),
    requestExport: (candidateId) =>
      call(`/v1/candidates/${encodeURIComponent(candidateId)}/exports`, { method: 'POST', headers: { 'Idempotency-Key': idem() } }),
  }
}
