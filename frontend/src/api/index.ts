import type { UnlockApi } from './client'
import { fixtureApi } from './fixtureApi'
import { createHttpApi } from './httpApi'
import { judgeJob, judgeOrigin, judgeHeaders } from './judgeSession'

const base = import.meta.env.VITE_UNLOCK_MODE === 'fixture' ? undefined : (import.meta.env.VITE_UNLOCK_API as string | undefined) ?? 'http://127.0.0.1:8000'

/** Connect locally by default. Illustrative mode requires VITE_UNLOCK_MODE=fixture. */
export const api: UnlockApi = base ? createHttpApi(() => { const job = judgeJob(); return job && judgeOrigin ? `${judgeOrigin}/jobs/${encodeURIComponent(job)}/view` : base }, () => judgeJob() ? judgeHeaders() : {}) : fixtureApi

/**
 * The sample assembly the landing page opens: the bundled illustrative record in
 * fixture mode, otherwise the coordinator's computed B02 fixture (its manifest id).
 */
export const SAMPLE_PROJECT_PATH = `/projects/${api.mode === 'fixture' ? 'prj_b02' : 'fixture_B02'}`

export * from './client'
