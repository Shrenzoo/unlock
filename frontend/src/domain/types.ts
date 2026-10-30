/**
 * Frontend mirror of the UNLOCK contracts (PRD §20, schema 1.0).
 * Units are millimetres, right-handed, Z up. IDs are opaque strings.
 * The frontend never derives verification status — it renders what a report says.
 */

export type Vec3 = [number, number, number]
export type Axis = 'X+' | 'X-' | 'Y+' | 'Y-' | 'Z+' | 'Z-'

/** Where a piece of evidence came from. Drives every status label in the UI. */
export type ProvenanceKind = 'live' | 'computed_earlier' | 'illustrative'

export interface Provenance {
  kind: ProvenanceKind
  /** content hash of the inputs, null when nothing was computed */
  input_hash: string | null
  computed_at: string | null
  engine_versions: Record<string, string> | null
  note: string
}

export type ComponentRole =
  | 'chassis'
  | 'cover'
  | 'bracket'
  | 'service_module'
  | 'electronics'
  | 'fastener'

export interface Component {
  id: string
  source_occurrence_path: string
  display_name: string
  role: ComponentRole
  fixed: boolean
  fixed_reason?: string
  replaceable: boolean
  removal_axes: Axis[]
  staging_region_id: string | null
  bounds_mm: { min: Vec3; max: Vec3 }
  template_family?: 'bridge_bracket_v1'
  shared_definition?: string
}

export interface ScrewRetainer {
  id: string
  kind: 'screw_retainer'
  fastener_id: string
  retained_component_ids: string[]
  host_component_id: string
  tool_id: string
  axis_world: Vec3
  head_origin_mm: Vec3
  extraction_distance_mm: number
  engagement_region_id: string
}

export interface PlanarSeat {
  id: string
  kind: 'planar_seat'
  component_a_id: string
  component_b_id: string
  region_a_id: string
  region_b_id: string
  outward_normal_world: Vec3
}

export type Connection = ScrewRetainer | PlanarSeat

export interface Tool {
  id: string
  type: 'screwdriver'
  tip_type: string
  shaft_radius_mm: number
  shaft_length_mm: number
  handle_radius_mm: number
  handle_length_mm: number
  approach_distance_mm: number
  permitted_axis: Axis
}

export type ConstraintKind =
  | 'fixed_geometry'
  | 'protected_region'
  | 'hole_axis'
  | 'envelope'
  | 'keep_out'
  | 'clearance'
  | 'template_bound'

export interface Constraint {
  id: string
  mandatory: boolean
  kind: ConstraintKind
  label: string
  component_ids: string[]
  /** human-readable limit with units, e.g. "≤ 0.01 mm" */
  limit: string
}

export interface BracketParameters {
  span_mm: number
  foot_width_mm: number
  foot_depth_mm: number
  foot_thickness_mm: number
  hole_diameter_mm: number
  post_width_mm: number
  post_depth_mm: number
  web_length_mm: number
  web_depth_mm: number
  web_thickness_mm: number
  web_underside_height_mm: number
}

export interface TemplateBinding {
  bracket_id: string
  family: 'bridge_bracket_v1'
  /** constructor v1 parameters, mm */
  parameters: BracketParameters
  editable_region_id: string
  templates: Array<{ id: 'T01' | 'T02'; label: string; domain: Record<string, number[]> }>
}

export interface KeepOut {
  id: string
  label: string
  min_mm: Vec3
  max_mm: Vec3
}

export interface AssemblyManifest {
  schema_version: '1.0'
  project_id: string
  assembly_id: string
  units: 'mm'
  frame: { handedness: 'right'; up: 'Z' }
  envelope_mm: { min: Vec3; max: Vec3 }
  components: Component[]
  connections: Connection[]
  tools: Tool[]
  constraints: Constraint[]
  keep_outs: KeepOut[]
  template_bindings: TemplateBinding[]
  provenance: { author: string; license: string; source: string }
}

/* ── planning ─────────────────────────────────────────────────────────── */

export type PlanStatus = 'feasible' | 'no_path_supported' | 'incomplete' | 'invalid_input' | 'cancelled'

export interface Step {
  action_id: string
  kind: 'REMOVE_FASTENER' | 'TRANSLATE_PART'
  component_id: string
  prerequisite_ids: string[]
  tool_id: string | null
  axis: Axis
  distance_mm: number
  /** exact segment endpoints in world mm — playback interpolates linearly between them */
  start_mm: Vec3
  end_mm: Vec3
  certificate_ids: string[]
}

export type EvidenceLevel = 'confirmed_witness' | 'insufficient_clearance' | 'proxy_unknown'

export interface Rejection {
  id: string
  action_kind: 'REMOVE_FASTENER' | 'TRANSLATE_PART' | 'TOOL_APPROACH'
  component_id: string
  axis: Axis
  obstacle_ids: string[]
  evidence_level: EvidenceLevel
  /** distance travelled before the witness pose, mm */
  witness_travel_mm: number | null
  explanation: string
  removed_ids?: string[]
  diagnostic?: boolean
}

export interface PlanResult {
  id: string
  status: PlanStatus
  revision_id: string
  target_id: string
  policy_version: string
  complete: boolean
  optimal_within_scope: boolean
  expanded_states: number
  elapsed_ms: number
  unresolved_transition_count: number
  steps: Step[]
  rejections: Rejection[]
}

/* ── redesign & verification ──────────────────────────────────────────── */

export interface Proposal {
  candidate_request_id: string
  bracket_id: string
  template_id: 'T01' | 'T02'
  parameters: Record<string, number>
  evidence_ids: string[]
  rationale: string
}

export type CheckResult = 'pass' | 'fail' | 'unknown' | 'not_applicable'

export interface CheckRecord {
  constraint_id: string
  label: string
  result: CheckResult
  measured: string | null
  limit: string
  evidence_ids: string[]
  explanation: string
}

export interface VerificationReport {
  id: string
  candidate_id: string
  status: 'passed' | 'failed' | 'unknown'
  constraint_hash: string
  checks: CheckRecord[]
  unverified_properties: string[]
}

export type CandidateState = 'proposed' | 'constructing' | 'checking' | 'failed' | 'checked' | 'no_supported_candidate'

export interface GeometryDiff {
  changed_component_id: string
  removed_volume_mm3: number
  /** world-space box of removed material, for the changed-region overlay */
  region_min_mm: Vec3
  region_max_mm: Vec3
  protected_unchanged: string[]
}

export interface Candidate {
  id: string
  proposal: Proposal
  state: CandidateState
  diff: GeometryDiff | null
  verification: VerificationReport | null
  revised_plan: PlanResult | null
  preview_artifact_id?: string | null
  input_hash?: string
  verified_improvement?: boolean
  metrics?: MetricRow[]
  review_decision?: 'accept' | 'reject'
  failure_summary?: string
}

/* ── run & events ─────────────────────────────────────────────────────── */

export type StageId =
  | 'inspect'
  | 'baseline'
  | 'obstruction'
  | 'interventions'
  | 'construct'
  | 'verify'
  | 'compare'

export interface StageEvent {
  sequence: number
  /** offset from run start, as recorded */
  t_ms: number
  stage: StageId
  state: 'started' | 'completed' | 'failed'
  message: string
  tool?: { name: string; args: string }
  evidence_ref?: string
}

export interface MetricRow {
  id: string
  label: string
  definition: string
  /** null when a value cannot be defined (e.g. infeasible baseline) — never a zero */
  original: string | null
  revised: string | null
  note?: string
}

export interface RunRecord {
  id: string
  revision_id: string
  target_id: string
  policy_version: string
  provenance: Provenance
  /** `live` is false for the offline scripted policy; absent on older records. */
  model: { id: string; provider: string; live?: boolean; turns?: number } | null
  baseline: PlanResult | null
  events: StageEvent[]
  candidates: Candidate[]
  selected_candidate_id: string | null
  metrics: MetricRow[]
  evidence_refs?: Record<string, string>
  state?: string
  outcome?: string | null
  explanation?: string | null
  ai_report_artifact_id?: string | null
  export?: { artifact_id: string; status: string; roundtrip_status: string } | null
}

/* ── projects ─────────────────────────────────────────────────────────── */

export interface ProjectSummary {
  id: string
  fixture_code: string
  name: string
  description: string
  occurrences: number | null
  revision: string | null
  status: 'ready' | 'not_authored'
  provenance: ProvenanceKind
  updated_at: string | null
}

export interface Revision {
  id: string
  project_id: string
  label: string
  input_hash: string
  manifest: AssemblyManifest
  constraint_hash?: string
  preview_artifact_id?: string
  provenance?: Provenance
  readiness: Array<{ field: string; ok: boolean; message: string }>
}

/* ── errors ───────────────────────────────────────────────────────────── */

export type ErrorCode =
  | 'INVALID_PACKAGE'
  | 'INVALID_MANIFEST'
  | 'UNSUPPORTED_SEMANTICS'
  | 'INVALID_SOLID'
  | 'LIMIT_EXCEEDED'
  | 'STALE_REVISION'
  | 'UNSUPPORTED_TEMPLATE'
  | 'CONSTRAINT_VIOLATION'
  | 'GEOMETRY_FAILED'
  | 'VERIFICATION_UNKNOWN'
  | 'MODEL_UNAVAILABLE'
  | 'MODEL_SCHEMA_ERROR'
  | 'NOT_FOUND'
  | 'FORBIDDEN'
  | 'CANCELLED'

export interface ErrorEnvelope {
  error_code: ErrorCode
  message: string
  retryable: boolean
  field_errors: Array<{ field: string; message: string }>
  evidence_ids: string[]
  run_id: string | null
}

/** Presentation meshes tessellated from actual BReps by a bounded backend worker. */
export interface PreviewMesh {
  authoritative: false
  units: 'm'
  scale_already_applied: true
  triangle_count: number
  components: Array<{ occurrence_id: string; vertices_m: Vec3[]; triangles: Array<[number, number, number]> }>
}
