import type { Dispatch, ReactNode } from 'react'
import type { Axis, Candidate, CheckRecord, Component, PlanResult, Revision, RunRecord, StageEvent } from '@/domain/types'
import { CheckResultTag, Glyph, ProvenanceTag } from '@/ui/Evidence'
import type { PartId } from '@/three/ModuleAssembly'
import { REPLAY_SCALE } from '@/api/fixtureApi'
import { api, type ServiceHealth } from '@/api'
import { trySetTarget } from './ComponentTree'
import { selectedCandidate, type Action, type WorkspaceState } from './model'

interface PanelProps {
  state: WorkspaceState
  dispatch: Dispatch<Action>
  run: RunRecord | null
  revision: Revision
  health?: ServiceHealth | null
  onRunBaseline: () => void
  onRunRedesign: () => void
  onDecide: (decision: 'accept' | 'reject') => void
  onExport: () => void
}

type Policy = { label: string; kind: 'none' | 'offline' | 'live' | 'unavailable' | 'recorded'; model?: string }

/**
 * Who chooses the edit, stated plainly. An offline scripted policy is never called
 * inference, and a model that never answered is never called a live run.
 */
export function decisionPolicy(run: RunRecord | null, health: ServiceHealth | null | undefined): Policy {
  const name = (provider: string) => (provider === 'meta' ? 'Meta' : provider)
  const m = run?.model
  if (run?.outcome === 'MODEL_UNAVAILABLE') {
    return { label: `${m ? `${name(m.provider)} ${m.id}` : 'Configured model'}: unavailable, no inference completed`, kind: 'unavailable', model: m?.id }
  }
  if (m) {
    if (m.live === false) return { label: 'Offline scripted policy, no model inference', kind: 'offline', model: m.id }
    if (m.live === true) return { label: `${name(m.provider)} ${m.id}, live inference`, kind: 'live', model: m.id }
    return { label: `Recorded policy (${m.provider})`, kind: 'recorded', model: m.id }
  }
  if (!health) return { label: 'Not connected to the engineering service', kind: 'none' }
  if (health.provider === 'mock') return { label: 'Offline scripted policy, no model inference', kind: 'offline', model: health.model }
  if (health.credentials === 'missing') return { label: `${name(health.provider)} ${health.model}: credentials missing, requests will report the model as unavailable`, kind: 'unavailable', model: health.model }
  return { label: `${name(health.provider)} ${health.model}, live inference (paid)`, kind: 'live', model: health.model }
}

/** T01/T02 labels can repeat their IDs; describe them instead of printing "T01 t01". */
const TEMPLATE_PLAIN: Record<string, string> = { T01: 'relief cut through the web', T02: 'web offset' }
function templateName(t: { id: string; label: string }) {
  return t.label && t.label.toLowerCase() !== t.id.toLowerCase() ? `${t.id} ${t.label.toLowerCase()}` : `${t.id} ${TEMPLATE_PLAIN[t.id] ?? ''}`.trim()
}

export function EvidencePanel(props: PanelProps) {
  const { state, dispatch } = props
  return (
    <aside className="panel" aria-label="Evidence">
      {state.notice && (
        <div className={`panel__notice panel__notice--${state.notice.tone}`} role={state.notice.tone === 'refuse' ? 'alert' : 'status'}>
          <Glyph kind={state.notice.tone === 'refuse' ? 'fail' : 'pass'} />
          <p>{state.notice.text}</p>
          <button type="button" aria-label="Dismiss" onClick={() => dispatch({ type: 'notice', notice: null })}>
            <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
              <path d="M2 2l6 6M8 2l-6 6" stroke="currentColor" strokeWidth="1.3" />
            </svg>
          </button>
        </div>
      )}
      <div className="panel__scroll">
        {state.mode === 'inspect' && <InspectPanel {...props} />}
        {state.mode === 'analyze' && <AnalyzePanel {...props} />}
        {state.mode === 'redesign' && <RedesignPanel {...props} />}
        {state.mode === 'compare' && <ComparePanel {...props} />}
        {state.mode === 'export' && <ExportPanel {...props} />}
      </div>
    </aside>
  )
}

/* ── shared pieces ──────────────────────────────────────────────────────── */

function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="psec">
      <header className="psec__head">
        <h2>{title}</h2>
        {aside}
      </header>
      {children}
    </section>
  )
}

const AXIS_ARROW: Record<Axis, string> = { 'X+': '→', 'X-': '←', 'Y+': '↗', 'Y-': '↙', 'Z+': '↑', 'Z-': '↓' }

function size(c: Component) {
  const d = [0, 1, 2].map((i) => c.bounds_mm.max[i] - c.bounds_mm.min[i])
  return `${d.map((x) => x.toFixed(1)).join(' × ')} mm`
}

const STAGE_LABEL: Record<StageEvent['stage'], string> = {
  inspect: 'Inspecting assembly',
  baseline: 'Searching removal paths',
  obstruction: 'Identifying obstruction',
  interventions: 'Evaluating supported modifications',
  construct: 'Constructing candidate',
  verify: 'Checking constraints',
  compare: 'Comparing repair paths',
}

function EventList({ events, running }: { events: StageEvent[]; running: boolean }) {
  // collapse started/completed pairs: the last record per stage-run wins
  const rows: StageEvent[] = []
  for (const e of events) {
    const prev = rows[rows.length - 1]
    if (prev && prev.stage === e.stage && prev.state === 'started' && e.state !== 'started') rows[rows.length - 1] = { ...e, tool: e.tool ?? prev.tool }
    else rows.push(e)
  }
  return (
    <ol className="events" aria-live="polite">
      {rows.map((e) => {
        const live = e.state === 'started' && running && e === rows[rows.length - 1]
        return (
          <li key={e.sequence} className={`events__row events__row--${e.state}`}>
            <span className="events__glyph">
              <Glyph kind={e.state === 'failed' ? 'fail' : live ? 'running' : e.state === 'started' ? 'pending' : 'pass'} />
            </span>
            <span className="events__stage">{STAGE_LABEL[e.stage]}</span>
            <span className="events__t mono">{(e.t_ms / 1000).toFixed(1)} s</span>
            <span className="events__msg">{e.message}</span>
            {e.tool && (
              <span className="events__tool mono">
                {e.tool.name}({e.tool.args})
              </span>
            )}
          </li>
        )
      })}
    </ol>
  )
}

function ReplayNote({ run }: { run: RunRecord }) {
  if (run.provenance.kind !== 'illustrative') return <p className="panel__fine"><ProvenanceTag provenance={run.provenance} /> Real engineering results; events are recorded by the backend worker.</p>
  return (
    <p className="panel__fine">
      Prepared sequence replayed at {Math.round(1 / REPLAY_SCALE)}× from recorded offsets. No planner, model or geometry service ran. <ProvenanceTag provenance={run.provenance} compact />
    </p>
  )
}

/* ── inspect ────────────────────────────────────────────────────────────── */

function InspectPanel({ state, dispatch, revision }: PanelProps) {
  const m = revision.manifest
  const sel = state.selected ? m.components.find((c) => c.id === state.selected) : null

  return (
    <>
      <Section title="Repair target">
        {state.target ? (
          <p className="target-line">
            <span className="chip chip--target mono">{state.target}</span>
            <span>Replaceable, removal along {m.components.find((c) => c.id === state.target)?.removal_axes.join(', ')}</span>
          </p>
        ) : (
          <p className="panel__empty">No target yet. Select a replaceable part, then set it as the target.</p>
        )}
      </Section>

      <Section title="Selected part">
        {sel ? <ComponentDetail c={sel} revision={revision} state={state} dispatch={dispatch} /> : <p className="panel__empty">Select a part in the viewport or the tree.</p>}
      </Section>

      <Section title="Manifest readiness" aside={<span className="psec__meta mono">{revision.readiness.filter((r) => r.ok).length} of {revision.readiness.length}</span>}>
        <ul className="ready">
          {revision.readiness.map((r) => (
            <li key={r.field}>
              <Glyph kind={r.ok ? 'pass' : 'fail'} />
              <span className="mono">{r.field}</span>
              <span>{r.message}</span>
            </li>
          ))}
        </ul>
      </Section>

      {state.target && (
        <div className="panel__cta">
          <button type="button" className="btn btn--primary" onClick={() => dispatch({ type: 'mode', mode: 'analyze' })}>
            <span className="btn__key" aria-hidden="true" />
            Analyze removal of {state.target}
          </button>
        </div>
      )}
    </>
  )
}

function ComponentDetail({ c, revision, state, dispatch }: { c: Component; revision: Revision; state: WorkspaceState; dispatch: Dispatch<Action> }) {
  const m = revision.manifest
  const retainedBy = m.connections.filter((k) => k.kind === 'screw_retainer' && k.retained_component_ids.includes(c.id))
  const retains = m.connections.find((k) => k.kind === 'screw_retainer' && k.fastener_id === c.id)
  const seat = m.connections.find((k) => k.kind === 'planar_seat' && (k.component_a_id === c.id || k.component_b_id === c.id))
  const id = c.id as PartId

  return (
    <div className="detail">
      <p className="detail__name">
        {c.display_name}
        <span className="mono">{c.id}</span>
      </p>
      <dl className="kv">
        <dt>Status</dt>
        <dd>{c.fixed ? 'Fixed' : c.replaceable ? 'Removable, replaceable' : 'Removable'}</dd>
        {c.fixed_reason && (
          <>
            <dt>Reason</dt>
            <dd>{c.fixed_reason}</dd>
          </>
        )}
        <dt>Removal</dt>
        <dd>{c.removal_axes.length ? c.removal_axes.map((a) => `${AXIS_ARROW[a]} ${a}`).join('  ') : 'None declared'}</dd>
        {retainedBy.length > 0 && (
          <>
            <dt>Retained by</dt>
            <dd className="mono">{retainedBy.map((k) => (k.kind === 'screw_retainer' ? k.fastener_id : '')).join(', ')}</dd>
          </>
        )}
        {retains && retains.kind === 'screw_retainer' && (
          <>
            <dt>Retains</dt>
            <dd>
              <span className="mono">{retains.retained_component_ids.join(', ')}</span> with <span className="mono">{retains.tool_id}</span>, {retains.extraction_distance_mm.toFixed(1)} mm out
            </dd>
          </>
        )}
        {seat && seat.kind === 'planar_seat' && (
          <>
            <dt>Seat</dt>
            <dd>Planar contact, separates along Z+</dd>
          </>
        )}
        <dt>Size</dt>
        <dd className="mono">{size(c)}</dd>
        {c.template_family && (
          <>
            <dt>Template</dt>
            <dd className="mono">{c.template_family}</dd>
          </>
        )}
        <dt>Occurrence</dt>
        <dd className="mono">{c.source_occurrence_path}</dd>
      </dl>
      <div className="detail__actions">
        {c.replaceable ? (
          <button type="button" className={`btn btn--sm ${state.target === id ? 'btn--quiet' : 'btn--primary'}`} disabled={state.target === id} onClick={() => trySetTarget(c, dispatch)}>
            {state.target === id ? 'Repair target' : 'Set as repair target'}
          </button>
        ) : (
          <button type="button" className="btn btn--quiet btn--sm" onClick={() => trySetTarget(c, dispatch)}>
            Set as repair target
          </button>
        )}
        <button type="button" className="btn btn--quiet btn--sm" aria-pressed={state.isolated === id} onClick={() => dispatch({ type: 'isolate', id: state.isolated === id ? null : id })}>
          {state.isolated === id ? 'End isolation' : 'Isolate'}
        </button>
        <button type="button" className="btn btn--quiet btn--sm" onClick={() => dispatch({ type: 'toggleHidden', id })}>
          {state.hidden.includes(id) ? 'Show' : 'Hide'}
        </button>
      </div>
      {state.hidden.length > 0 && <p className="panel__fine">Hidden parts still take part in every analysis. Hiding only changes the view.</p>}
    </div>
  )
}

/* ── analyze ────────────────────────────────────────────────────────────── */

const PLAN_HEADLINE: Record<PlanResult['status'], string> = {
  feasible: 'Feasible route found',
  no_path_supported: 'No path within supported operations',
  incomplete: 'Search incomplete',
  invalid_input: 'Input not valid for analysis',
  cancelled: 'Analysis cancelled',
}

function AnalyzePanel({ state, dispatch, run, onRunBaseline }: PanelProps) {
  const b = run?.baseline
  const st = state.baseline.status
  return (
    <>
      <Section title="Baseline analysis" aside={<span className="psec__meta mono">{b?.policy_version ?? 'policy_v1'}</span>}>
        <p className="target-line">
          <span className="chip chip--target mono">{state.target}</span>
          <span>Straight moves along declared axes, budget 30 s or 4,096 states</span>
        </p>
        {(st === 'idle' || st === 'failed') && (
          <div className="panel__cta panel__cta--inline">
            <button type="button" className="btn btn--primary" onClick={onRunBaseline}>
              <span className="btn__key" aria-hidden="true" />
              Run baseline analysis
            </button>
          </div>
        )}
        {st !== 'idle' && <EventList events={state.baseline.events} running={st === 'running'} />}
        {st !== 'idle' && run && <ReplayNote run={run} />}
      </Section>

      {st === 'done' && b && (
        <>
          <Section title="Result">
            <p className={`outcome outcome--${b.status}`}>
              <Glyph kind={b.status === 'feasible' ? 'pass' : 'fail'} />
              {PLAN_HEADLINE[b.status]}
            </p>
            <p className="panel__body">
              Search {b.complete ? 'complete' : 'incomplete'}: {b.expanded_states} states, {(b.elapsed_ms / 1000).toFixed(1)} s recorded, {b.unresolved_transition_count} unresolved transitions. {b.status === 'feasible' ? 'The listed route passed independent replay.' : b.status === 'no_path_supported' ? 'No route exists within the supported finite operations and declared constraints.' : 'Analysis did not establish a complete result.'} This says nothing about routes outside the supported operations.
            </p>
          </Section>

          <Section title="Actions before the block" aside={<span className="psec__meta mono">{b.steps.length}</span>}>
            <ol className="steps">
              {b.steps.map((s, i) => (
                <li key={s.action_id}>
                  <span className="mono steps__n">{i + 1}</span>
                  <span>{s.kind === 'REMOVE_FASTENER' ? 'Remove' : 'Translate'}</span>
                  <span className="mono">{s.component_id}</span>
                  <span className="mono steps__d">
                    {s.axis} {s.distance_mm.toFixed(1)}
                  </span>
                </li>
              ))}
            </ol>
          </Section>

          <Section title="Blocked actions" aside={<span className="psec__meta">Select to show the witness</span>}>
            <ul className="blocks">
              {b.rejections.map((r) => (
                <li key={r.id}>
                  <button type="button" className="block" aria-pressed={state.witness === r.id} onClick={() => dispatch({ type: 'witness', id: state.witness === r.id ? null : r.id })}>
                    <span className="block__head">
                      <span className="mono">{r.id.slice(0, 12)}</span>
                      <span className={`level level--${r.evidence_level}`}>{r.evidence_level === 'confirmed_witness' ? 'Confirmed witness' : r.evidence_level === 'proxy_unknown' ? 'Proxy overlap, unknown' : 'Insufficient clearance'}</span>
                    </span>
                    <span className="block__what">
                      {r.action_kind === 'TOOL_APPROACH' ? 'Driver approach to' : 'Translate'} <span className="mono">{r.component_id}</span> {r.axis}, blocked by <span className="mono">{r.obstacle_ids.join(', ')}</span>
                    </span>
                    <span className="block__why">{r.explanation}</span>
                    {r.diagnostic && <span className="block__tag">Diagnostic, not a planner step</span>}
                  </button>
                </li>
              ))}
            </ul>
          </Section>

          <div className="panel__cta">
            <button type="button" className="btn btn--primary" onClick={() => dispatch({ type: 'mode', mode: 'redesign' })}>
              <span className="btn__key" aria-hidden="true" />
              Explore a redesign
            </button>
          </div>
        </>
      )}
    </>
  )
}

/* ── redesign ───────────────────────────────────────────────────────────── */

function RedesignPanel({ state, dispatch, run, revision, health, onRunRedesign }: PanelProps) {
  if (!run) return null
  const st = state.redesign.status
  const cand = selectedCandidate(run, state)
  const binding = revision.manifest.template_bindings[0]
  const visible = st === 'done' ? run.candidates : []
  const policy = decisionPolicy(st === 'done' ? run : null, health)

  return (
    <>
      <Section title="Redesign" aside={<span className="psec__meta mono">{binding?.family ?? 'No supported template family'}</span>}>
        <p className="panel__body">
          The decision policy below chooses one supported edit to <span className="mono">{binding?.bracket_id ?? 'the selected component'}</span> and its parameters. The server builds the solid, and a separate verifier rebuilds it and checks every declared constraint. The policy cannot mark its own proposal as valid.
        </p>
        <dl className="kv kv--tight">
          <dt>Decision policy</dt>
          <dd data-testid="decision-policy" data-policy={policy.kind}>
            {policy.label}
            {policy.model && <> · <span className="mono">{policy.model}</span></>}
          </dd>
          <dt>Budget</dt>
          <dd>3 candidates, 12 tool calls, 120 s</dd>
          <dt>Templates</dt>
          <dd>{binding?.templates.map(templateName).join(', ')}</dd>
        </dl>
        {(st === 'idle' || st === 'failed') && (
          <div className="panel__cta panel__cta--inline">
            <button type="button" className="btn btn--primary" onClick={onRunRedesign}>
              <span className="btn__key" aria-hidden="true" />
              Request redesign
            </button>
          </div>
        )}
        {st !== 'idle' && <EventList events={state.redesign.events} running={st === 'running'} />}
        {st !== 'idle' && <ReplayNote run={run} />}
      </Section>

      {st === 'done' && (
        <Section title="Engineering outcome">
          <p className="panel__body" data-testid="run-outcome" data-outcome={run.outcome ?? ''} data-run-id={run.id}>{run.outcome?.replaceAll('_', ' ') ?? 'Recorded result'}</p>
          <p className="panel__body">{run.explanation ?? 'Inspect the candidate evidence below.'}</p>
          <p className="panel__body panel__note" data-testid="run-provenance">{run.provenance.note}</p>
        </Section>
      )}
      {visible.length > 0 && (
        <Section title="Candidates" aside={<span className="psec__meta mono">{visible.length} of 3</span>}>
          <ul className="cands">
            {visible.map((c, i) => (
              <li key={c.id}>
                <button type="button" className={`cand cand--${c.state}`} aria-pressed={state.candidateId === c.id} onClick={() => dispatch({ type: 'candidate', id: c.id })}>
                  <span className="cand__n mono">{i + 1}</span>
                  <span className="cand__what">
                    <strong>
                      {templateName(revision.manifest.template_bindings[0].templates.find((t) => t.id === c.proposal.template_id) ?? { id: c.proposal.template_id, label: '' })}
                    </strong>
                    <span className="mono">{paramSummary(c)}</span>
                  </span>
                  <span className="cand__state">{<CheckResultTag result={c.state === 'failed' ? 'fail' : c.state === 'checked' ? 'pass' : 'unknown'} provenance={run.provenance.kind} />}</span>
                </button>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {cand && st === 'done' && <CandidateDetail c={cand} run={run} revision={revision} dispatch={dispatch} />}
    </>
  )
}

function paramSummary(c: Candidate) {
  const p = c.proposal.parameters
  if (c.proposal.template_id === 'T02') return `offset_y ${p.offset_y_mm > 0 ? '+' : ''}${p.offset_y_mm} mm`
  return `${p.width_mm} × ${p.depth_mm} mm at (${p.center_x_mm}, ${p.center_y_mm})`
}

function CandidateDetail({ c, run, revision, dispatch }: { c: Candidate; run: RunRecord; revision: Revision; dispatch: Dispatch<Action> }) {
  const tpl = revision.manifest.template_bindings[0].templates.find((t) => t.id === c.proposal.template_id)
  return (
    <>
      <Section title={`Candidate ${c.id.replace('cand_', '')}`} aside={<span className="psec__meta mono">{c.proposal.candidate_request_id}</span>}>
        {c.failure_summary && (
          <p className="outcome outcome--no_path_supported">
            <Glyph kind="fail" />
            {c.failure_summary}
          </p>
        )}
        <table className="params">
          <caption className="visually-hidden">Template parameters</caption>
          <thead>
            <tr>
              <th scope="col">Parameter</th>
              <th scope="col" className="num">
                Value
              </th>
              <th scope="col">Allowed</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(c.proposal.parameters).map(([k, v]) => (
              <tr key={k}>
                <td className="mono">{k}</td>
                <td className="num mono">{v}</td>
                <td className="mono params__dom">{tpl?.domain[k]?.join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <blockquote className="rationale">
          <p>{c.proposal.rationale}</p>
          <footer>
            Cites{' '}
            {c.proposal.evidence_ids.map((id) => (
              <button
                key={id}
                type="button"
                className="chip mono"
                onClick={() => {
                  if (run.baseline?.rejections.some((r) => r.id === (run.evidence_refs?.[id] ?? id))) {
                    dispatch({ type: 'mode', mode: 'analyze' })
                    dispatch({ type: 'witness', id: run.evidence_refs?.[id] ?? id })
                  } else if (api.mode === 'http' && run.ai_report_artifact_id) {
                    window.open(api.artifactUrl(run.ai_report_artifact_id) + '#' + encodeURIComponent(run.evidence_refs?.[id] ?? id), '_blank', 'noopener')
                  }
                }}
                title={run.baseline?.rejections.some((r) => r.id === (run.evidence_refs?.[id] ?? id)) ? 'Open this evidence in the analysis' : 'Verification report'}
              >
                {id}
              </button>
            ))}
          </footer>
        </blockquote>
        {c.diff && (
          <dl className="kv kv--tight">
            <dt>Changed</dt>
            <dd>
              <span className="mono">{c.diff.changed_component_id}</span>, {c.diff.removed_volume_mm3.toLocaleString()} mm³ removed
            </dd>
            <dt>Protected</dt>
            <dd>{c.diff.protected_unchanged.join(', ')}</dd>
          </dl>
        )}
      </Section>

      {c.verification && (
        <Section title="Constraint checks" aside={<span className="psec__meta mono">{c.verification.constraint_hash}</span>}>
          <Checks checks={c.verification.checks} run={run} />
          {c.verification.unverified_properties.length > 0 && (
            <div className="unverified">
              <p>Not assessed</p>
              <ul>
                {c.verification.unverified_properties.map((u) => (
                  <li key={u}>{u}</li>
                ))}
              </ul>
            </div>
          )}
        </Section>
      )}

      {c.state === 'checked' && (
        <div className="panel__cta">
          <button type="button" className="btn btn--primary" onClick={() => dispatch({ type: 'mode', mode: 'compare' })}>
            <span className="btn__key" aria-hidden="true" />
            Compare with the original
          </button>
        </div>
      )}
    </>
  )
}

function Checks({ checks, run }: { checks: CheckRecord[]; run: RunRecord }) {
  return (
    <ul className="checks">
      {checks.map((k) => (
        <li key={k.constraint_id}>
          <details>
            <summary>
              <span className="checks__label">{k.label}</span>
              <CheckResultTag result={k.result} provenance={run.provenance.kind} />
            </summary>
            <dl className="kv kv--tight">
              <dt>Measured</dt>
              <dd className="mono">{k.measured ?? 'Not evaluated'}</dd>
              <dt>Limit</dt>
              <dd className="mono">{k.limit}</dd>
              <dt>Evidence</dt>
              <dd className="mono">{k.evidence_ids.join(', ') || 'None'}</dd>
              <dt>Note</dt>
              <dd>{k.explanation}</dd>
            </dl>
          </details>
        </li>
      ))}
    </ul>
  )
}

/* ── compare ────────────────────────────────────────────────────────────── */

function ComparePanel({ state, run, onDecide }: PanelProps) {
  if (!run) return null
  const c = selectedCandidate(run, state)
  const ver = c?.verification
  const counts = ver ? { pass: ver.checks.filter((k) => k.result === 'pass').length, fail: ver.checks.filter((k) => k.result === 'fail').length, unknown: ver.checks.filter((k) => k.result === 'unknown').length } : null
  return (
    <>
      <Section title="Outcome">
        <p className="outcome outcome--scoped">
          <Glyph kind="pass" />
          <span>
            Geometry checks recorded for <span className="mono">{run.target_id}</span> under <span className="mono">{run.policy_version}</span>, listed operations, declared contacts and clearances.
          </span>
        </p>
        <p className="panel__warn">Strength, electrical safety, manufacturing feasibility and restored product function were not assessed.</p>
        <p className="panel__fine">
          <ProvenanceTag provenance={run.provenance} /> {run.provenance.kind === 'illustrative' ? 'These are illustrative fixture values.' : 'These values come from current independent verification and deterministic planning.'}
        </p>
      </Section>

      <Section title="Original and revised" aside={<span className="psec__meta mono">{ver?.constraint_hash}</span>}>
        <table className="metrics">
          <thead>
            <tr>
              <th scope="col">Metric</th>
              <th scope="col">Original</th>
              <th scope="col">Revised</th>
            </tr>
          </thead>
          <tbody>
            {(c?.metrics ?? run.metrics).map((m) => (
              <tr key={m.id}>
                <th scope="row" title={m.definition}>
                  {m.label}
                </th>
                <td className={m.original === null ? 'is-undefined' : ''} title={m.original === null ? m.note ?? 'Not defined for an infeasible route' : undefined}>
                  {m.original ?? 'Not defined'}
                </td>
                <td className="mono-num">{m.revised ?? 'Not defined'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="panel__fine">The original route is infeasible within supported operations, so its counts are not defined and no percentage is computed. Same target, policy and constraint hash on both sides.</p>
      </Section>

      {counts && (
        <Section title="Mandatory checks">
          <p className="tally">
            <span>
              <strong>{counts.pass}</strong> pass
            </span>
            <span>
              <strong>{counts.fail}</strong> fail
            </span>
            <span>
              <strong>{counts.unknown}</strong> unknown
            </span>
          </p>
        </Section>
      )}

      <Section title="Review">
        <ul className="review">
          <li>
            <span>Geometry checks</span>
            <span>{run.provenance.kind === 'illustrative' ? 'Illustrative, verifier not run' : ver?.status ?? 'Not checked'}</span>
          </li>
          <li>
            <span>Engineer acceptance</span>
            <span>{c?.review_decision ?? 'Not recorded'}</span>
          </li>
          <li>
            <span>Engineering release</span>
            <span>Not assessed</span>
          </li>
        </ul>
        <div className="detail__actions">
          <button type="button" className="btn btn--primary btn--sm" disabled={api.mode !== 'http' || !c?.verified_improvement || c.review_decision === 'accept'} onClick={() => onDecide('accept')} aria-describedby="accept-why">
            Accept for export
          </button>
          <button type="button" className="btn btn--quiet btn--sm" disabled={api.mode !== 'http' || !c} onClick={() => onDecide('reject')} aria-describedby="accept-why">
            Reject candidate
          </button>
        </div>
        <p id="accept-why" className="panel__fine">
          Acceptance records a review decision under the current input hash. Only a verified improvement can be accepted for export. Illustrative candidates cannot be accepted.
        </p>
      </Section>
    </>
  )
}

/* ── export ─────────────────────────────────────────────────────────────── */

const PACKAGE = [
  ['original.step', 'Original assembly, unchanged'],
  ['revised.step', 'Revised assembly'],
  ['changed_bracket.step', 'Changed bracket only'],
  ['manifest.json', 'Revised manifest'],
  ['template_parameters.json', 'Template parameters and constructor version'],
  ['metrics.json', 'Defined metrics, original and revised'],
  ['paths.json', 'Removal and insertion segments'],
  ['verification.json', 'Per-constraint results and evidence'],
  ['roundtrip.json', 'STEP reimport check of the revised assembly'],
  ['geometry_difference.json', 'Measured removed and added material'],
  ['ai_run.json', 'Decision record: tool calls, candidates, policy'],
  ['preview.json', 'Presentation mesh, not CAD output'],
  ['attribution.txt', 'Fixture provenance'],
  ['limitations.txt', 'Human-readable summary with limitations'],
  ['bundle.json', 'SHA-256 of every file above'],
]

function ExportPanel({ run, state, health, onExport }: PanelProps) {
  if (!run) return null
  const c = selectedCandidate(run, state)
  const accepted = c?.review_decision === 'accept'
  const exporting = state.redesign.status === 'running'
  const exported = run.export && run.export.review_candidate_id === c?.id ? run.export : null
  const policy = decisionPolicy(run, health)
  return (
    <>
      <Section title="Export package">
        <p className="panel__body">STEP carries editable solid geometry. It does not keep the originating feature history or native mates. A GLB preview is never the CAD output.</p>
        <ul className="pkg">
          {PACKAGE.filter(([f]) => !(run.export?.status === 'changed_part_only' && f === 'revised.step')).map(([f, d]) => (
            <li key={f}>
              <span className="mono">{f}</span>
              <span>{d}</span>
            </li>
          ))}
        </ul>
        <div className="detail__actions">
          <button type="button" className={`btn btn--sm ${exported ? 'btn--quiet' : 'btn--primary'}`} disabled={api.mode !== 'http' || !accepted || exporting} onClick={onExport} aria-describedby="export-why">
            {exporting ? 'Checking and packaging…' : exported ? 'Create the package again' : 'Create checked package'}
          </button>
          {exported && (
            // A plain link: the browser treats the attachment as a download, so no popup blocker can swallow it.
            <a className="btn btn--primary btn--sm" href={api.artifactUrl(exported.artifact_id)} download data-testid="export-download" data-artifact-id={exported.artifact_id}>
              Download checked package (ZIP)
            </a>
          )}
        </div>
        <p id="export-why" className="panel__fine" role="status">
          {exported
            ? `Export ${exported.status.replaceAll('_', ' ')}; STEP round trip ${exported.roundtrip_status}. Package SHA-256 ${exported.artifact_id.slice(0, 12)}…`
            : exporting
              ? 'Reconstructing the solid, replanning the route and reimporting the STEP output. This takes up to a minute.'
              : accepted
                ? 'Ready. Export reconstructs the solid, replans the route and reimports the STEP output before the package is offered for download.'
                : 'Accept the checked candidate first. Export reconstructs the solid, replans the route and reimports the STEP output before download.'}{' '}
          <ProvenanceTag provenance={run.provenance} compact />
        </p>
      </Section>
      <Section title="Attribution">
        <p className="panel__body">
          Decision policy: {policy.label}{policy.model ? ` (${policy.model})` : ''}. Fixture provenance and engineering limitations are included in the export. Redistribution rights must be confirmed before publication.
        </p>
      </Section>
    </>
  )
}

