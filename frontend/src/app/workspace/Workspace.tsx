import { lazy, Suspense, useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { api, ServiceNotConnected, type ServiceHealth } from '@/api'
import type { Revision, RunRecord } from '@/domain/types'
import { Link, navigate } from '@/router'
import { Mark } from '@/ui/Logo'
import { ProvenanceTag } from '@/ui/Evidence'
import { ComponentTree } from './ComponentTree'
import { EvidencePanel } from './Panels'
import { Viewport } from './Viewport'
import { MODES, initialState, modeAvailable, reducer, type Mode } from './model'
import './workspace.css'

const LiveViewport = lazy(() => import('./LiveViewport').then((m) => ({ default: m.LiveViewport })))

const MODE_LABEL: Record<Mode, string> = {
  inspect: 'Inspect',
  analyze: 'Analyze',
  redesign: 'Redesign',
  compare: 'Compare',
  export: 'Export',
}

export default function Workspace({ projectId }: { projectId: string }) {
  const [revision, setRevision] = useState<Revision | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [run, setRun] = useState<RunRecord | null>(null)
  const [health, setHealth] = useState<ServiceHealth | null>(null)
  const [state, dispatch] = useReducer(reducer, initialState)
  const jobs = useRef<{ controller: AbortController; id: string | null } | null>(null)
  const generation = useRef(0)
  const choseMode = useRef(false)

  const stopActive = useCallback(() => {
    generation.current += 1
    const active = jobs.current
    jobs.current = null
    active?.controller.abort()
    if (active?.id) void api.cancelJob(active.id).catch(() => {})
  }, [])

  useEffect(() => {
    let live = true
    choseMode.current = false
    setRevision(null)
    setError(null)
    api.latestRevisionId(projectId).then((id) => api.getRevision(id)).then((r) => { if (live) setRevision(r) })
      .catch((e) => {
        if (!live) return
        if (e instanceof ServiceNotConnected) setError(`There is no prepared data for ${projectId} in this build.`)
        // fetch() rejects with TypeError only when no HTTP response arrived at all.
        else if (e instanceof TypeError) setError(`Cannot reach the UNLOCK engineering service at ${api.origin}. Start the backend, then reload this page.`)
        else setError((e as Error).message)
      })
    api.health().then((h) => { if (live) setHealth(h) }).catch(() => { if (live) setHealth(null) })
    return () => { live = false; stopActive() }
  }, [projectId, stopActive])

  // Reload recovery: a run in ?run= is restored from the backend when it belongs to
  // this exact revision. Nothing is re-executed; the persisted record is shown.
  const restoring = useRef<RunRecord | null>(null)
  useEffect(() => {
    if (!revision) return
    const id = new URLSearchParams(window.location.search).get('run') ?? health?.demo_run_id
    if (!id) return
    let live = true
    api.getRun(id).then((r) => {
      if (!live || r.revision_id !== revision.id) return
      restoring.current = r
      dispatch({ type: 'target', id: r.target_id })
    }).catch(() => { /* an unknown or foreign run leaves a clean workspace */ })
    return () => { live = false }
  }, [revision, health?.demo_run_id])

  useEffect(() => {
    stopActive()
    const restored = restoring.current
    if (restored && restored.target_id === state.target) {
      restoring.current = null
      setRun(restored)
      if (restored.baseline) dispatch({ type: 'job', job: 'baseline', status: 'done' })
      const redesigned = restored.outcome != null || restored.candidates.length > 0
      if (redesigned) {
        dispatch({ type: 'job', job: 'redesign', status: 'done' })
        const accepted = restored.candidates.find((c) => c.review_decision === 'accept')
        dispatch({ type: 'candidate', id: accepted?.id ?? restored.selected_candidate_id })
      }
      if (!choseMode.current) dispatch({ type: 'mode', mode: redesigned ? 'redesign' : 'analyze' })
      if (restored.state === 'queued' || restored.state === 'running') {
        dispatch({ type: 'notice', notice: { tone: 'info', text: 'A job for this run was still in progress when the page loaded. Reload again shortly to see its persisted result.' } })
      }
      return stopActive
    }
    setRun(null)
    // A newly chosen target starts a new analysis; drop the old run from the address.
    if (state.target && window.location.search.includes('run=')) { const q = new URLSearchParams(window.location.search); q.delete('run'); navigate(window.location.pathname + (q.size ? '?' + q.toString() : ''), { replace: true }) }
    return stopActive
  }, [state.target, stopActive])

  const execute = useCallback(async (kind: 'baseline' | 'redesign' | 'export') => {
    if (health?.access === 'read_only') {
      dispatch({ type: 'notice', notice: { tone: 'info', text: 'Read-only demonstration. This view uses previously computed CAD evidence; new engineering jobs require authenticated access.' } })
      return
    }
    if (!revision || !state.target || (kind !== 'baseline' && !run)) return
    stopActive()
    const current = generation.current
    const ctrl = new AbortController()
    const active = { controller: ctrl, id: null as string | null }
    jobs.current = active
    const jobKind = kind === 'baseline' ? 'baseline' : 'redesign'
    dispatch({ type: 'job', job: jobKind, status: 'running' })
    let runId = run?.id
    try {
      const result = kind === 'baseline'
        ? await api.startRun(revision.id, { target_id: state.target, policy_id: 'planner_v1', constraint_hash: revision.constraint_hash })
        : kind === 'redesign' ? await api.requestRedesign(run!.id)
        : await api.requestExport(state.candidateId!)
      active.id = result.job_id
      if (current !== generation.current) { void api.cancelJob(result.job_id).catch(() => {}); return }
      if ('run_id' in result) runId = result.run_id as string
      if (!runId) throw new Error('The backend did not return a run identity.')
      if (kind === 'baseline') navigate(`${window.location.pathname}?run=${encodeURIComponent(runId)}`, { replace: true })
      await api.streamEvents(result.job_id, (event) => {
        if (current === generation.current) dispatch({ type: 'event', job: jobKind, event })
      }, ctrl.signal)
      if (current !== generation.current || ctrl.signal.aborted) return
      const fresh = await api.getRun(runId)
      if (current !== generation.current || fresh.target_id !== state.target || fresh.revision_id !== revision.id) return
      setRun(fresh)
      dispatch({ type: 'job', job: jobKind, status: 'done' })
      // Export keeps the reviewed candidate selected; the panel then offers a plain
      // download link (a delayed window.open would be swallowed by popup blockers).
      if (kind === 'redesign') dispatch({ type: 'candidate', id: fresh.selected_candidate_id })
    } catch (e) {
      if (current !== generation.current) return
      if (runId) {
        const saved = await api.getRun(runId).catch(() => null)
        if (saved && current === generation.current && saved.target_id === state.target) setRun(saved)
      }
      if (current !== generation.current) return
      dispatch({ type: 'job', job: jobKind, status: 'failed' })
      dispatch({ type: 'notice', notice: { tone: 'refuse', text: (e as Error).message } })
    } finally { if (current === generation.current) jobs.current = null }
  }, [revision, run, state.target, state.candidateId, stopActive, health?.access])

  const decide = useCallback(async (decision: 'accept' | 'reject') => {
    if (health?.access === 'read_only') return
    const c = run?.candidates.find((c) => c.id === state.candidateId)
    if (!run || !c?.input_hash) return
    const current = generation.current
    try {
      await api.decide(c.id, decision, c.input_hash)
      const fresh = await api.getRun(run.id)
      if (current !== generation.current || fresh.target_id !== state.target || fresh.revision_id !== revision?.id) return
      setRun(fresh)
      dispatch({ type: 'notice', notice: { tone: 'info', text: decision === 'accept' ? 'Accepted for checked export. Engineering release remains unassessed.' : 'Candidate rejected; evidence is preserved.' } })
    } catch (e) { if (current === generation.current) dispatch({ type: 'notice', notice: { tone: 'refuse', text: (e as Error).message } }) }
  }, [run, state.candidateId, state.target, revision?.id, health?.access])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (state.isolated) dispatch({ type: 'isolate', id: null })
      else dispatch({ type: 'select', id: null })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [state.isolated])

  if (error) {
    return (
      <main className="ws-empty">
        <Mark size={28} />
        <h1>Project unavailable</h1>
        <p>{error}</p>
        <Link to="/projects" className="btn btn--quiet">
          Back to projects
        </Link>
      </main>
    )
  }

  if (!revision) {
    return (
      <main className="ws-empty" aria-busy="true">
        <Mark size={28} />
        <p>Loading revision…</p>
      </main>
    )
  }

  return (
    <div className="ws">
      <header className="topbar">
        <Link to="/projects" className="topbar__home" aria-label="Back to projects">
          <Mark size={18} />
        </Link>
        <div className="topbar__project">
          <span className="topbar__name">{revision.manifest.assembly_id}</span>
          <span className="mono topbar__rev">{revision.label}</span>
        </div>
        <span className={`topbar__target ${state.target ? 'is-set' : ''}`}>
          {state.target ? (
            <>
              Target <span className="mono">{state.target}</span>
            </>
          ) : (
            'No target'
          )}
        </span>

        <nav className="modes" aria-label="Workflow">
          <ol>
            {MODES.map((m, i) => {
              const avail = modeAvailable(m, state, run)
              return (
                <li key={m}>
                  <button
                    type="button"
                    aria-current={state.mode === m ? 'step' : undefined}
                    disabled={!avail.ok}
                    title={avail.ok ? undefined : avail.why}
                    onClick={() => { choseMode.current = true; dispatch({ type: 'mode', mode: m }) }}
                  >
                    <span className="mono">{i + 1}</span>
                    {MODE_LABEL[m]}
                  </button>
                </li>
              )
            })}
          </ol>
        </nav>

        <div className="topbar__end">
          <ProvenanceTag provenance={run?.provenance ?? revision.provenance ?? { kind: 'illustrative', input_hash: null, computed_at: null, engine_versions: null, note: 'Bundled illustrative fixture' }} compact />
          {(state.baseline.status === 'running' || state.redesign.status === 'running') && <button type="button" className="btn btn--quiet btn--sm" onClick={() => { stopActive(); dispatch({ type: 'job', job: state.baseline.status === 'running' ? 'baseline' : 'redesign', status: 'failed' }); dispatch({ type: 'notice', notice: { tone: 'info', text: 'Cancellation requested. Completed baseline evidence is preserved.' } }) }}>Cancel job</button>}
          <button type="button" className="btn btn--quiet btn--sm" disabled={!modeAvailable('export', state, run).ok} title={modeAvailable('export', state, run).why} onClick={() => dispatch({ type: 'mode', mode: 'export' })}>
            Export
          </button>
        </div>
      </header>

      <ComponentTree manifest={revision.manifest} selected={state.selected} target={state.target} hidden={state.hidden} isolated={state.isolated} dispatch={dispatch} />

      <main className="ws__view" aria-label="Assembly viewport">
        {api.mode === 'http' ? <Suspense fallback={<p>Loading CAD viewer…</p>}><LiveViewport revision={revision} state={state} dispatch={dispatch} run={run} /></Suspense> : <Viewport state={state} dispatch={dispatch} run={run} />}
      </main>

      <EvidencePanel state={state} dispatch={dispatch} run={run} revision={revision} health={health} onRunBaseline={() => void execute('baseline')} onRunRedesign={() => void execute('redesign')} onDecide={(d) => void decide(d)} onExport={() => void execute('export')} />

      <p className="ws__narrow" role="note">
        The workspace is built for screens at least 1280 px wide. Evidence and controls stay available below.
      </p>
    </div>
  )
}
