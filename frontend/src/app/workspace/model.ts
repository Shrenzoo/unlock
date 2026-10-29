import type { Candidate, PlanResult, Rejection, RunRecord, StageEvent, Step, Vec3 } from '@/domain/types'
import { PART_IDS, isPartId, type AssemblyView, type PartId, type Relief } from '@/three/ModuleAssembly'

/* ── workspace state ────────────────────────────────────────────────────── */

export const MODES = ['inspect', 'analyze', 'redesign', 'compare', 'export'] as const
export type Mode = (typeof MODES)[number]

export type JobStatus = 'idle' | 'running' | 'done' | 'failed'

export interface WorkspaceState {
  mode: Mode
  selected: string | null
  hovered: string | null
  target: string | null
  hidden: string[]
  isolated: string | null
  /** 0 = opaque, 1 = context parts nearly invisible */
  xray: number
  exploded: boolean
  baseline: { status: JobStatus; events: StageEvent[] }
  redesign: { status: JobStatus; events: StageEvent[] }
  witness: string | null
  candidateId: string | null
  showDiff: boolean
  notice: { tone: 'info' | 'refuse'; text: string } | null
}

export const initialState: WorkspaceState = {
  mode: 'inspect',
  selected: null,
  hovered: null,
  target: null,
  hidden: [],
  isolated: null,
  xray: 0,
  exploded: false,
  baseline: { status: 'idle', events: [] },
  redesign: { status: 'idle', events: [] },
  witness: null,
  candidateId: null,
  showDiff: true,
  notice: null,
}

export type Action =
  | { type: 'mode'; mode: Mode }
  | { type: 'select'; id: string | null }
  | { type: 'hover'; id: string | null }
  | { type: 'target'; id: string | null }
  | { type: 'toggleHidden'; id: string }
  | { type: 'showAll' }
  | { type: 'isolate'; id: string | null }
  | { type: 'xray'; value: number }
  | { type: 'explode'; value: boolean }
  | { type: 'job'; job: 'baseline' | 'redesign'; status: JobStatus }
  | { type: 'event'; job: 'baseline' | 'redesign'; event: StageEvent }
  | { type: 'witness'; id: string | null }
  | { type: 'candidate'; id: string | null }
  | { type: 'diff'; value: boolean }
  | { type: 'notice'; notice: WorkspaceState['notice'] }

const COVER_PARTS: PartId[] = ['cover', 'screw_c1', 'screw_c2', 'screw_c3', 'screw_c4']

export function reducer(s: WorkspaceState, a: Action): WorkspaceState {
  switch (a.type) {
    case 'mode': {
      const next: WorkspaceState = { ...s, mode: a.mode, witness: a.mode === 'analyze' ? s.witness : null, notice: null }
      // the edited bracket sits under the cover: hide it once, visibly and reversibly
      const inside = false // Fixture-specific hiding is controlled explicitly by the viewer.
      const missing = COVER_PARTS.filter((id) => !s.hidden.includes(id))
      if (inside && missing.length === COVER_PARTS.length) {
        next.hidden = [...s.hidden, ...missing]
        next.notice = { tone: 'info', text: 'Top cover and its screws are hidden to show the bracket. Hidden parts still take part in every check.' }
      }
      return next
    }
    case 'select':
      return { ...s, selected: a.id }
    case 'hover':
      return s.hovered === a.id ? s : { ...s, hovered: a.id }
    case 'target':
      // a changed target invalidates every result computed for the previous one (FR018)
      return a.id === s.target
        ? s
        : { ...s, target: a.id, baseline: { status: 'idle', events: [] }, redesign: { status: 'idle', events: [] }, candidateId: null, witness: null, notice: null }
    case 'toggleHidden':
      return { ...s, hidden: s.hidden.includes(a.id) ? s.hidden.filter((h) => h !== a.id) : [...s.hidden, a.id] }
    case 'showAll':
      return { ...s, hidden: [], isolated: null }
    case 'isolate':
      return { ...s, isolated: a.id }
    case 'xray':
      return { ...s, xray: a.value }
    case 'explode':
      return { ...s, exploded: a.value }
    case 'job':
      return { ...s, [a.job]: { ...s[a.job], status: a.status, events: a.status === 'running' ? [] : s[a.job].events } }
    case 'event':
      return { ...s, [a.job]: { ...s[a.job], events: [...s[a.job].events, a.event] } }
    case 'witness':
      return { ...s, witness: a.id }
    case 'candidate':
      return { ...s, candidateId: a.id }
    case 'diff':
      return { ...s, showDiff: a.value }
    case 'notice':
      return { ...s, notice: a.notice }
  }
}

/* ── playback ───────────────────────────────────────────────────────────── */

export interface Segment {
  kind: 'step' | 'blocked'
  component: PartId
  step?: Step
  rejection?: Rejection
  label: string
}

const fmt = (n: number) => n.toFixed(1)

/** Ordered playback segments. An infeasible plan ends at its first blocking rejection. */
export function segmentsFor(plan: PlanResult): Segment[] {
  const segs: Segment[] = plan.steps
    .filter((s) => isPartId(s.component_id))
    .map((s) => ({
      kind: 'step',
      component: s.component_id as PartId,
      step: s,
      label: `${s.kind === 'REMOVE_FASTENER' ? 'Remove fastener' : 'Translate'} ${s.component_id}, ${s.axis} ${fmt(s.distance_mm)} mm`,
    }))
  if (plan.status !== 'feasible') {
    const block = plan.rejections.find((r) => !r.diagnostic)
    if (block && isPartId(block.component_id)) {
      segs.push({ kind: 'blocked', component: block.component_id, rejection: block, label: `Blocked: ${block.action_kind === 'TOOL_APPROACH' ? 'driver approach to' : 'translate'} ${block.component_id}` })
    }
  }
  return segs
}

/** Time easing only. Spatial interpolation between stored endpoints stays linear (PRD §19). */
const easeTime = (f: number) => (f <= 0 ? 0 : f >= 1 ? 1 : f * f * (3 - 2 * f))

export interface Pose {
  offsets: Partial<Record<PartId, Vec3>>
  done: Set<PartId>
  active: PartId | null
  obstruction: PartId | null
  tool: AssemblyView['tool']
  probe: AssemblyView['probe']
}

export function poseAt(segs: Segment[], t: number): Pose {
  const pose: Pose = { offsets: {}, done: new Set(), active: null, obstruction: null, tool: null, probe: null }
  segs.forEach((seg, i) => {
    const f = easeTime(t - i)
    if (f <= 0) return
    if (seg.kind === 'step' && seg.step) {
      const { start_mm: a, end_mm: b } = seg.step
      pose.offsets[seg.component] = [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]
      if (f >= 1) pose.done.add(seg.component)
      else pose.active = seg.component
    } else if (seg.rejection) {
      applyWitness(pose, seg.rejection, f)
    }
  })
  return pose
}

export function applyWitness(pose: Pose, r: Rejection, f = 1) {
  if (r.action_kind === 'TOOL_APPROACH') {
    // straight driver approach from above, stopping on the obstacle top face (z 42.0)
    pose.tool = { tip: 150 - (150 - 42) * f, opacity: 0.4, blocked: f >= 1 }
  } else {
    pose.probe = { z: (r.witness_travel_mm ?? 0) * f, opacity: 0.45, tone: f >= 1 ? 'obstruction' : 'target' }
  }
  if (f >= 1) pose.obstruction = (r.obstacle_ids[0] as PartId) ?? null
}

/* ── view composition ───────────────────────────────────────────────────── */

const EXPLODED: Partial<Record<PartId, Vec3>> = {
  cover: [0, 0, 46],
  screw_c1: [0, 0, 72],
  screw_c2: [0, 0, 72],
  screw_c3: [0, 0, 72],
  screw_c4: [0, 0, 72],
  screw_b1: [0, 0, 14],
  screw_b2: [0, 0, 14],
  screw_f1: [0, 0, 14],
}

export function reliefFor(c: Candidate | null | undefined): Relief | null {
  if (!c || c.proposal.template_id !== 'T01' || c.state === 'failed') return null
  const p = c.proposal.parameters
  return { cx: p.center_x_mm, cy: p.center_y_mm, w: p.width_mm, d: p.depth_mm }
}

export interface Compose {
  state: WorkspaceState
  pose: Pose | null
  relief: Relief | null
}

export function composeView(view: AssemblyView, { state: s, pose, relief }: Compose) {
  const finished = pose && pose.done.has(s.target as PartId)
  for (const id of PART_IDS) {
    const p = view.parts[id]
    p.visible = !s.hidden.includes(id) && (!s.isolated || s.isolated === id)
    p.hover = s.hovered === id
    const focus = id === s.selected || id === s.target
    let opacity = s.xray > 0 && !focus ? 1 - s.xray * 0.88 : 1
    if (pose?.done.has(id) && id !== s.target) opacity = Math.min(opacity, id.startsWith('screw') ? 0.1 : 0.16)
    if (finished && id !== s.target) opacity = Math.min(opacity, 0.32)
    p.opacity = opacity
    p.tone = pose?.obstruction === id ? 'obstruction' : id === s.selected ? 'selected' : id === s.target ? 'target' : 'default'
    const e = s.exploded && !pose ? EXPLODED[id] : undefined
    const o = pose?.offsets[id]
    p.offset[0] = (e?.[0] ?? 0) + (o?.[0] ?? 0)
    p.offset[1] = (e?.[1] ?? 0) + (o?.[1] ?? 0)
    p.offset[2] = (e?.[2] ?? 0) + (o?.[2] ?? 0)
    p.fade = undefined
  }
  view.relief = relief
  view.tool = pose?.tool ?? null
  view.probe = pose?.probe ?? null
}

/* ── derived helpers ────────────────────────────────────────────────────── */

export function baselineDone(s: WorkspaceState) {
  return s.baseline.status === 'done'
}

export function selectedCandidate(run: RunRecord | null, s: WorkspaceState) {
  return run?.candidates.find((c) => c.id === s.candidateId) ?? null
}

export function modeAvailable(mode: Mode, s: WorkspaceState, run: RunRecord | null): { ok: boolean; why?: string } {
  switch (mode) {
    case 'inspect':
      return { ok: true }
    case 'analyze':
      return s.target ? { ok: true } : { ok: false, why: 'Set a repair target first' }
    case 'redesign':
      return baselineDone(s) ? { ok: true } : { ok: false, why: 'Run the baseline analysis first' }
    case 'compare':
    case 'export': {
      const c = selectedCandidate(run, s)
      return c && c.state === 'checked' ? { ok: true } : { ok: false, why: 'Choose a candidate whose checks completed' }
    }
  }
}
