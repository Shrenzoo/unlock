import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { api, ServiceNotConnected } from '@/api'
import type { Revision, RunRecord } from '@/domain/types'
import { Link } from '@/router'
import { Mark } from '@/ui/Logo'
import { ProvenanceTag } from '@/ui/Evidence'
import { ComponentTree } from './ComponentTree'
import { EvidencePanel } from './Panels'
import { Viewport } from './Viewport'
import { MODES, initialState, modeAvailable, reducer, type Mode } from './model'
import './workspace.css'

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
  const [state, dispatch] = useReducer(reducer, initialState)
  const jobs = useRef<AbortController | null>(null)

  useEffect(() => {
    let live = true
    api
      .latestRevisionId(projectId)
      .then((id) => api.getRevision(id))
      .then((r) => live && setRevision(r))
      .catch((e) => live && setError(e instanceof ServiceNotConnected ? `There is no prepared data for ${projectId} in this build.` : (e as Error).message))
    return () => {
      live = false
      jobs.current?.abort()
    }
  }, [projectId])

  // a new target abandons any job still streaming for the old one
  useEffect(() => {
    jobs.current?.abort()
    setRun(null)
  }, [state.target])

  const runBaseline = useCallback(async () => {
    if (!revision || !state.target) return
    jobs.current?.abort()
    const ctrl = new AbortController()
    jobs.current = ctrl
    dispatch({ type: 'job', job: 'baseline', status: 'running' })
    const { run_id, job_id } = await api.startRun(revision.id, { target_id: state.target, policy_id: 'policy_v1' })
    setRun(await api.getRun(run_id))
    await api.streamEvents(job_id, (event) => dispatch({ type: 'event', job: 'baseline', event }), ctrl.signal)
    if (ctrl.signal.aborted) return
    dispatch({ type: 'job', job: 'baseline', status: 'done' })
  }, [revision, state.target])

  const runRedesign = useCallback(async () => {
    if (!run) return
    jobs.current?.abort()
    const ctrl = new AbortController()
    jobs.current = ctrl
    dispatch({ type: 'job', job: 'redesign', status: 'running' })
    const { job_id } = await api.requestRedesign(run.id)
    await api.streamEvents(job_id, (event) => dispatch({ type: 'event', job: 'redesign', event }), ctrl.signal)
    if (ctrl.signal.aborted) return
    const fresh = await api.getRun(run.id)
    setRun(fresh)
    dispatch({ type: 'job', job: 'redesign', status: 'done' })
    dispatch({ type: 'candidate', id: fresh.selected_candidate_id })
  }, [run])

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
          <span className="topbar__name">Trapped fan bridge</span>
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
                    onClick={() => dispatch({ type: 'mode', mode: m })}
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
          <ProvenanceTag provenance={run?.provenance ?? { kind: 'illustrative', input_hash: null, computed_at: null, engine_versions: null, note: 'Bundled fixture' }} compact />
          <button type="button" className="btn btn--quiet btn--sm" disabled={!modeAvailable('export', state, run).ok} title={modeAvailable('export', state, run).why} onClick={() => dispatch({ type: 'mode', mode: 'export' })}>
            Export
          </button>
        </div>
      </header>

      <ComponentTree manifest={revision.manifest} selected={state.selected} target={state.target} hidden={state.hidden} isolated={state.isolated} dispatch={dispatch} />

      <main className="ws__view" aria-label="Assembly viewport">
        <Viewport state={state} dispatch={dispatch} run={run} />
      </main>

      <EvidencePanel state={state} dispatch={dispatch} run={run} revision={revision} onRunBaseline={runBaseline} onRunRedesign={runRedesign} />

      <p className="ws__narrow" role="note">
        The workspace is built for screens at least 1280 px wide. Evidence and controls stay available below.
      </p>
    </div>
  )
}
