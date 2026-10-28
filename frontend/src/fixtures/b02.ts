/**
 * Fixture B02 — trapped fan bridge (PRD §21).
 *
 * ILLUSTRATIVE DATA. Authored by hand for the frontend build so every screen
 * has realistic, internally consistent content. Nothing here was produced by
 * the geometry worker, the planner or Muse Spark Open. All records carry
 * provenance.kind = 'illustrative' and the UI must label them that way.
 *
 * Geometry is in world millimetres, Z up. The bracket follows constructor v1
 * (PRD §10.4): feet at ±span/2, posts on the inner foot edge, web on top.
 */
import type {
  AssemblyManifest,
  Candidate,
  Component,
  MetricRow,
  PlanResult,
  ProjectSummary,
  Revision,
  RunRecord,
  StageEvent,
  Step,
  Vec3,
} from '@/domain/types'

const ILLUSTRATIVE_NOTE =
  'Prepared demonstration data. No geometry, planning or model service was run to produce it.'

export const B02_RELIEF = { center_x_mm: 0, center_y_mm: -20, width_mm: 52, depth_mm: 16 }

const COVER_SCREWS: Array<{ k: string; at: [number, number] }> = [
  { k: 'c1', at: [-72, -47] },
  { k: 'c2', at: [72, -47] },
  { k: 'c3', at: [-72, 47] },
  { k: 'c4', at: [72, 47] },
]

const coverScrews: Component[] = COVER_SCREWS.map(({ k, at: [x, y] }, i) => ({
  id: `screw_${k}`,
  source_occurrence_path: `/B02/screw_m3x10:${i + 1}`,
  display_name: `Cover screw ${k.toUpperCase()}`,
  role: 'fastener',
  fixed: false,
  replaceable: false,
  removal_axes: ['Z+'],
  staging_region_id: 'stage_above',
  bounds_mm: { min: [x - 2.8, y - 2.8, 51], max: [x + 2.8, y + 2.8, 63.5] },
  shared_definition: 'def_screw_m3x10',
}))

const bracketScrews: Component[] = [-48, 48].map((x, i) => ({
  id: `screw_b${i + 1}`,
  source_occurrence_path: `/B02/screw_m3x8_tl:${i + 1}`,
  display_name: `Bracket screw B${i + 1}`,
  role: 'fastener',
  fixed: true,
  fixed_reason: 'Thread-locked. Not removable in a service operation (declared).',
  replaceable: false,
  removal_axes: [],
  staging_region_id: null,
  bounds_mm: { min: [x - 3, -3, 0], max: [x + 3, 3, 10.5] },
  shared_definition: 'def_screw_m3x8_tl',
}))

export const b02Manifest: AssemblyManifest = {
  schema_version: '1.0',
  project_id: 'prj_b02',
  assembly_id: 'asm_b02_trapped_fan_bridge',
  units: 'mm',
  frame: { handedness: 'right', up: 'Z' },
  envelope_mm: { min: [-80, -55, 0], max: [80, 55, 64] },
  components: [
    {
      id: 'chassis',
      source_occurrence_path: '/B02/chassis:1',
      display_name: 'Chassis',
      role: 'chassis',
      fixed: true,
      fixed_reason: 'Grounded base. Declared workholding.',
      replaceable: false,
      removal_axes: [],
      staging_region_id: null,
      bounds_mm: { min: [-80, -55, 0], max: [80, 55, 58] },
    },
    {
      id: 'cover',
      source_occurrence_path: '/B02/cover:1',
      display_name: 'Top cover',
      role: 'cover',
      fixed: false,
      replaceable: false,
      removal_axes: ['Z+'],
      staging_region_id: 'stage_above',
      bounds_mm: { min: [-80, -55, 58], max: [80, 55, 61] },
    },
    ...coverScrews,
    {
      id: 'bridge_bracket',
      source_occurrence_path: '/B02/bridge_bracket:1',
      display_name: 'Bridge bracket',
      role: 'bracket',
      fixed: true,
      fixed_reason: 'Retained by thread-locked screws. Not a service operation (declared).',
      replaceable: false,
      removal_axes: [],
      staging_region_id: null,
      bounds_mm: { min: [-56, -34, 4], max: [56, 34, 42] },
      template_family: 'bridge_bracket_v1',
    },
    ...bracketScrews,
    {
      id: 'fan_module',
      source_occurrence_path: '/B02/fan_module:1',
      display_name: 'Fan module',
      role: 'service_module',
      fixed: false,
      replaceable: true,
      removal_axes: ['Z+'],
      staging_region_id: 'stage_above',
      bounds_mm: { min: [-15, -26, 6], max: [27, -14, 36] },
    },
    {
      id: 'screw_f1',
      source_occurrence_path: '/B02/screw_m3x8:1',
      display_name: 'Fan screw',
      role: 'fastener',
      fixed: false,
      replaceable: false,
      removal_axes: ['Z+'],
      staging_region_id: 'stage_above',
      bounds_mm: { min: [18.2, -22.8, 2], max: [23.8, -17.2, 10.5] },
    },
    {
      id: 'pcb_controller',
      source_occurrence_path: '/B02/pcb_controller:1',
      display_name: 'Controller board',
      role: 'electronics',
      fixed: true,
      fixed_reason: 'Outside the target dependency closure. Held fixed for this run.',
      replaceable: false,
      removal_axes: [],
      staging_region_id: null,
      bounds_mm: { min: [-74, 16, 10], max: [-24, 48, 16] },
    },
  ],
  connections: [
    ...COVER_SCREWS.map(({ k, at: [x, y] }) => ({
      id: `ret_cover_${k}`,
      kind: 'screw_retainer' as const,
      fastener_id: `screw_${k}`,
      retained_component_ids: ['cover'],
      host_component_id: 'chassis',
      tool_id: 'driver_ph1',
      axis_world: [0, 0, 1] as Vec3,
      head_origin_mm: [x, y, 61] as Vec3,
      extraction_distance_mm: 12,
      engagement_region_id: `engage_cover_${k}`,
    })),
    {
      id: 'ret_fan_f1',
      kind: 'screw_retainer',
      fastener_id: 'screw_f1',
      retained_component_ids: ['fan_module'],
      host_component_id: 'chassis',
      tool_id: 'driver_ph1',
      axis_world: [0, 0, 1],
      head_origin_mm: [21, -20, 8],
      extraction_distance_mm: 10,
      engagement_region_id: 'engage_fan_f1',
    },
    {
      id: 'seat_fan',
      kind: 'planar_seat',
      component_a_id: 'fan_module',
      component_b_id: 'chassis',
      region_a_id: 'fan_underside',
      region_b_id: 'seat_pad_top',
      outward_normal_world: [0, 0, 1],
    },
  ],
  tools: [
    {
      id: 'driver_ph1',
      type: 'screwdriver',
      tip_type: 'PH1',
      shaft_radius_mm: 3,
      shaft_length_mm: 80,
      handle_radius_mm: 14,
      handle_length_mm: 100,
      approach_distance_mm: 90,
      permitted_axis: 'Z+',
    },
  ],
  constraints: [
    { id: 'k_fixed', mandatory: true, kind: 'fixed_geometry', label: 'Fixed components unchanged', component_ids: ['chassis', 'pcb_controller'], limit: 'hash match' },
    { id: 'k_pads', mandatory: true, kind: 'protected_region', label: 'Bracket mounting pads', component_ids: ['bridge_bracket'], limit: '≤ 0.01 mm' },
    { id: 'k_posts', mandatory: true, kind: 'protected_region', label: 'Bracket posts', component_ids: ['bridge_bracket'], limit: '≤ 0.01 mm' },
    { id: 'k_holes', mandatory: true, kind: 'hole_axis', label: 'Foot hole axes', component_ids: ['bridge_bracket'], limit: '≤ 0.01 mm, ≤ 0.1°' },
    { id: 'k_env', mandatory: true, kind: 'envelope', label: 'Design envelope', component_ids: ['bridge_bracket'], limit: 'inside housing, 0.5 mm guard' },
    { id: 'k_keepout', mandatory: true, kind: 'keep_out', label: 'Cable reserve keep-out', component_ids: ['bridge_bracket'], limit: 'no intersection' },
    { id: 'k_collide', mandatory: true, kind: 'fixed_geometry', label: 'Assembled collision', component_ids: [], limit: 'no undeclared overlap' },
    { id: 'k_clear', mandatory: true, kind: 'clearance', label: 'Path clearance', component_ids: ['fan_module', 'screw_f1'], limit: '≥ 0.5 mm' },
    { id: 'k_web', mandatory: true, kind: 'template_bound', label: 'Remaining web', component_ids: ['bridge_bracket'], limit: '≥ 6.0 mm each side' },
  ],
  keep_outs: [{ id: 'ko_cable', label: 'Cable reserve', min_mm: [-20, 36, 6], max_mm: [20, 52, 30] }],
  template_bindings: [
    {
      bracket_id: 'bridge_bracket',
      family: 'bridge_bracket_v1',
      editable_region_id: 'web',
      parameters: {
        span_mm: 96,
        foot_width_mm: 16,
        foot_depth_mm: 24,
        foot_thickness_mm: 4,
        hole_diameter_mm: 3.4,
        post_width_mm: 6,
        post_depth_mm: 24,
        web_length_mm: 92,
        web_depth_mm: 68,
        web_thickness_mm: 4,
        web_underside_height_mm: 34,
      },
      templates: [
        {
          id: 'T01',
          label: 'Rectangular web relief',
          domain: {
            center_x_mm: [-4, 0, 4],
            center_y_mm: [-24, -20, -16],
            width_mm: [40, 46, 52],
            depth_mm: [12, 16, 20],
          },
        },
        { id: 'T02', label: 'Bounded web offset', domain: { offset_y_mm: [-12, 12, 24, 36] } },
      ],
    },
  ],
  provenance: {
    author: 'UNLOCK team (synthetic fixture)',
    license: 'Proposed CC BY 4.0, not yet granted',
    source: 'Hand-authored for the frontend build',
  },
}

const POLICY = 'policy_v1'

/** Step paths are relative offsets from the assembled pose, world mm. */
const coverSteps: Step[] = [
  ...COVER_SCREWS.map(({ k }) => ({
    action_id: `a_${k}`,
    kind: 'REMOVE_FASTENER' as const,
    component_id: `screw_${k}`,
    prerequisite_ids: [],
    tool_id: 'driver_ph1',
    axis: 'Z+' as const,
    distance_mm: 12,
    start_mm: [0, 0, 0] as Vec3,
    end_mm: [0, 0, 12] as Vec3,
    certificate_ids: [`cert_${k}`],
  })),
  {
    action_id: 'a_cover',
    kind: 'TRANSLATE_PART',
    component_id: 'cover',
    prerequisite_ids: ['a_c1', 'a_c2', 'a_c3', 'a_c4'],
    tool_id: null,
    axis: 'Z+',
    distance_mm: 60,
    start_mm: [0, 0, 0],
    end_mm: [0, 0, 60],
    certificate_ids: ['cert_cover'],
  },
]

export const b02Baseline: PlanResult = {
  id: 'plan_b02_base',
  status: 'no_path_supported',
  revision_id: 'rev_b02_A',
  target_id: 'fan_module',
  policy_version: POLICY,
  complete: true,
  optimal_within_scope: false,
  expanded_states: 23,
  elapsed_ms: 4120,
  unresolved_transition_count: 0,
  steps: coverSteps,
  rejections: [
    {
      id: 'rej_tool_f1',
      action_kind: 'TOOL_APPROACH',
      component_id: 'screw_f1',
      axis: 'Z+',
      obstacle_ids: ['bridge_bracket'],
      evidence_level: 'confirmed_witness',
      witness_travel_mm: null,
      explanation: 'Driver shaft volume meets the bracket web between z 38.0 and 42.0 mm. The fan screw cannot be reached from Z+.',
    },
    {
      id: 'rej_sweep_fan',
      action_kind: 'TRANSLATE_PART',
      component_id: 'fan_module',
      axis: 'Z+',
      obstacle_ids: ['bridge_bracket'],
      evidence_level: 'confirmed_witness',
      witness_travel_mm: 2,
      explanation: 'Diagnostic sweep with the retainer assumed released. The fan meets the bracket web after 2.0 mm of travel.',
      diagnostic: true,
    },
  ],
}

const revisedPlan: PlanResult = {
  id: 'plan_b02_c2',
  status: 'feasible',
  revision_id: 'rev_b02_C2',
  target_id: 'fan_module',
  policy_version: POLICY,
  complete: true,
  optimal_within_scope: true,
  expanded_states: 17,
  elapsed_ms: 3380,
  unresolved_transition_count: 0,
  steps: [
    ...coverSteps,
    {
      action_id: 'a_f1',
      kind: 'REMOVE_FASTENER',
      component_id: 'screw_f1',
      prerequisite_ids: ['a_cover'],
      tool_id: 'driver_ph1',
      axis: 'Z+',
      distance_mm: 10,
      start_mm: [0, 0, 0],
      end_mm: [0, 0, 10],
      certificate_ids: ['cert_f1'],
    },
    {
      action_id: 'a_fan',
      kind: 'TRANSLATE_PART',
      component_id: 'fan_module',
      prerequisite_ids: ['a_f1'],
      tool_id: null,
      axis: 'Z+',
      distance_mm: 64,
      start_mm: [0, 0, 0],
      end_mm: [0, 0, 64],
      certificate_ids: ['cert_fan'],
    },
  ],
  rejections: [],
}

export const b02Candidates: Candidate[] = [
  {
    id: 'cand_1',
    state: 'failed',
    proposal: {
      candidate_request_id: 'proposal_1',
      bracket_id: 'bridge_bracket',
      template_id: 'T02',
      parameters: { offset_y_mm: 36 },
      evidence_ids: ['rej_tool_f1', 'rej_sweep_fan'],
      rationale: 'Move the web away from the fan along local Y so the lift-out corridor and driver approach clear it.',
    },
    diff: null,
    revised_plan: null,
    failure_summary: 'Web would reach y 70.0 mm. The envelope ends at 51.5 mm.',
    verification: {
      id: 'ver_1',
      candidate_id: 'cand_1',
      status: 'failed',
      constraint_hash: 'k#4be1…09',
      unverified_properties: [],
      checks: [
        { constraint_id: 'k_env', label: 'Design envelope', result: 'fail', measured: 'y max 70.0 mm', limit: '≤ 51.5 mm', evidence_ids: ['ev_env_1'], explanation: 'Offset web passes through the rear housing wall.' },
        { constraint_id: 'k_pads', label: 'Bracket mounting pads', result: 'pass', measured: '0.00 mm', limit: '≤ 0.01 mm', evidence_ids: ['ev_pad_1'], explanation: 'Feet regenerated unchanged.' },
        { constraint_id: 'k_clear', label: 'Path clearance', result: 'not_applicable', measured: null, limit: '≥ 0.5 mm', evidence_ids: [], explanation: 'Not evaluated after a mandatory failure.' },
      ],
    },
  },
  {
    id: 'cand_2',
    state: 'checked',
    proposal: {
      candidate_request_id: 'proposal_2',
      bracket_id: 'bridge_bracket',
      template_id: 'T01',
      parameters: { ...B02_RELIEF },
      evidence_ids: ['rej_tool_f1', 'rej_sweep_fan', 'ver_1'],
      rationale: 'Relieve the web directly above the fan and its screw. Feet, posts and holes stay inside the protected regions.',
    },
    diff: {
      changed_component_id: 'bridge_bracket',
      removed_volume_mm3: 3328,
      region_min_mm: [-26, -28, 38],
      region_max_mm: [26, -12, 42],
      protected_unchanged: ['Mounting pads', 'Foot hole axes', 'Posts'],
    },
    revised_plan: revisedPlan,
    verification: {
      id: 'ver_2',
      candidate_id: 'cand_2',
      status: 'passed',
      constraint_hash: 'k#4be1…09',
      unverified_properties: ['Structural strength and stiffness', 'Electrical safety and EMC shielding', 'Manufacturing feasibility', 'Restored product function'],
      checks: [
        { constraint_id: 'k_fixed', label: 'Fixed components unchanged', result: 'pass', measured: '2 of 2 hashes match', limit: 'hash match', evidence_ids: ['ev_fix_2'], explanation: 'Chassis and controller board untouched.' },
        { constraint_id: 'k_pads', label: 'Bracket mounting pads', result: 'pass', measured: '0.00 mm', limit: '≤ 0.01 mm', evidence_ids: ['ev_pad_2'], explanation: 'Named pad regions unchanged.' },
        { constraint_id: 'k_posts', label: 'Bracket posts', result: 'pass', measured: '0.00 mm', limit: '≤ 0.01 mm', evidence_ids: ['ev_post_2'], explanation: 'Relief stays 14.0 mm clear of the posts.' },
        { constraint_id: 'k_holes', label: 'Foot hole axes', result: 'pass', measured: '0.000 mm, 0.00°', limit: '≤ 0.01 mm, ≤ 0.1°', evidence_ids: ['ev_hole_2'], explanation: 'Both axes unchanged.' },
        { constraint_id: 'k_env', label: 'Design envelope', result: 'pass', measured: 'inside, 9.5 mm margin', limit: '0.5 mm guard', evidence_ids: ['ev_env_2'], explanation: 'Material only removed.' },
        { constraint_id: 'k_keepout', label: 'Cable reserve keep-out', result: 'pass', measured: 'no intersection', limit: 'no intersection', evidence_ids: ['ev_ko_2'], explanation: 'Relief is 48.0 mm from the reserve.' },
        { constraint_id: 'k_collide', label: 'Assembled collision', result: 'pass', measured: '0 overlaps', limit: 'no undeclared overlap', evidence_ids: ['ev_col_2'], explanation: 'Declared seat contact only.' },
        { constraint_id: 'k_clear', label: 'Path clearance', result: 'pass', measured: '2.0 mm', limit: '≥ 0.5 mm', evidence_ids: ['ev_clr_2'], explanation: 'Lower bound over fan lift-out and driver approach.' },
        { constraint_id: 'k_web', label: 'Remaining web', result: 'pass', measured: '6.0 mm front strip', limit: '≥ 6.0 mm', evidence_ids: ['ev_web_2'], explanation: 'At the declared minimum.' },
      ],
    },
  },
]

export const b02Events: StageEvent[] = [
  { sequence: 1, t_ms: 0, stage: 'inspect', state: 'started', message: 'Inspecting assembly roles and relations', tool: { name: 'inspect_assembly', args: '12 components' } },
  { sequence: 2, t_ms: 640, stage: 'inspect', state: 'completed', message: '12 occurrences, 6 connections, 0 unresolved fields' },
  { sequence: 3, t_ms: 700, stage: 'baseline', state: 'started', message: 'Searching removal sequences for fan_module', tool: { name: 'analyze_removal', args: 'fan_module, policy_v1' } },
  { sequence: 4, t_ms: 4820, stage: 'baseline', state: 'completed', message: 'No path within supported operations. 23 states, search complete', evidence_ref: 'plan_b02_base' },
  { sequence: 5, t_ms: 4900, stage: 'obstruction', state: 'started', message: 'Identifying obstruction', tool: { name: 'inspect_blocker', args: 'rej_tool_f1' } },
  { sequence: 6, t_ms: 5600, stage: 'obstruction', state: 'completed', message: 'Bracket web blocks the driver approach and the lift-out', evidence_ref: 'rej_tool_f1' },
  { sequence: 7, t_ms: 5700, stage: 'interventions', state: 'started', message: 'Evaluating supported modifications', tool: { name: 'list_interventions', args: 'bridge_bracket' } },
  { sequence: 8, t_ms: 6200, stage: 'interventions', state: 'completed', message: 'T01 web relief, 81 values. T02 web offset, 4 values' },
  { sequence: 9, t_ms: 6300, stage: 'construct', state: 'started', message: 'Constructing candidate 1, T02 offset +36 mm', tool: { name: 'construct_candidate', args: 'T02 {offset_y_mm: 36}' } },
  { sequence: 10, t_ms: 9100, stage: 'verify', state: 'failed', message: 'Candidate 1 rejected. Envelope exceeded by 18.5 mm', tool: { name: 'verify_candidate', args: 'cand_1' }, evidence_ref: 'ver_1' },
  { sequence: 11, t_ms: 9300, stage: 'construct', state: 'started', message: 'Constructing candidate 2, T01 relief 52 × 16 mm', tool: { name: 'construct_candidate', args: 'T01 {0, -20, 52, 16}' } },
  { sequence: 12, t_ms: 12400, stage: 'verify', state: 'started', message: 'Checking constraints and replanning', tool: { name: 'verify_candidate', args: 'cand_2' } },
  { sequence: 13, t_ms: 17800, stage: 'verify', state: 'completed', message: '9 mandatory checks recorded, 0 failed, 0 unknown', evidence_ref: 'ver_2' },
  { sequence: 14, t_ms: 17900, stage: 'compare', state: 'started', message: 'Comparing repair paths', tool: { name: 'compare_candidates', args: 'cand_2' } },
  { sequence: 15, t_ms: 18300, stage: 'compare', state: 'completed', message: 'Baseline infeasible. Candidate 2 feasible in 7 operations' },
]

export const b02Metrics: MetricRow[] = [
  { id: 'feasible', label: 'Feasible removal', definition: 'Target reaches the staging region through permitted checked moves.', original: 'No path within supported operations', revised: 'Feasible' },
  { id: 'ops', label: 'Operations', definition: 'Accepted primitive actions through target extraction.', original: null, revised: '7', note: 'Not defined for an infeasible route' },
  { id: 'unrelated', label: 'Unrelated parts removed', definition: 'Removed non-fastener occurrences, excluding the target.', original: null, revised: '1' },
  { id: 'fasteners', label: 'Fasteners removed', definition: 'Unique fastener occurrences removed before staging.', original: null, revised: '5' },
  { id: 'tools', label: 'Tool changes', definition: 'Transitions between different tools. One PH1 driver throughout.', original: null, revised: '0' },
  { id: 'clearance', label: 'Clearance lower bound', definition: 'Minimum certified gap to non-contact obstacles over accepted paths.', original: null, revised: '2.0 mm' },
  { id: 'modified', label: 'Modified parts', definition: 'Occurrences whose solid geometry differs.', original: '0', revised: '1, bridge_bracket' },
  { id: 'checks', label: 'Constraint outcomes', definition: 'Mandatory checks: passed, failed, unknown.', original: 'Not run', revised: '9 passed, 0 failed, 0 unknown' },
]

export const b02Run: RunRecord = {
  id: 'run_b02_demo',
  revision_id: 'rev_b02_A',
  target_id: 'fan_module',
  policy_version: POLICY,
  provenance: { kind: 'illustrative', input_hash: null, computed_at: null, engine_versions: null, note: ILLUSTRATIVE_NOTE },
  model: null,
  baseline: b02Baseline,
  events: b02Events,
  candidates: b02Candidates,
  selected_candidate_id: 'cand_2',
  metrics: b02Metrics,
}

export const b02Revision: Revision = {
  id: 'rev_b02_A',
  project_id: 'prj_b02',
  label: 'Rev A',
  input_hash: 'not computed',
  manifest: b02Manifest,
  readiness: [
    { field: 'components', ok: true, message: '12 leaf occurrences (limit 5 to 12)' },
    { field: 'connections', ok: true, message: '5 screw retainers, 1 planar seat' },
    { field: 'tools', ok: true, message: 'driver_ph1, straight approach Z+' },
    { field: 'template_bindings', ok: true, message: 'bridge_bracket bound to bridge_bracket_v1' },
    { field: 'staging', ok: true, message: 'stage_above reachable from Z+' },
  ],
}

export const projects: ProjectSummary[] = [
  {
    id: 'prj_b02',
    fixture_code: 'B02',
    name: 'Trapped fan bridge',
    description: 'A bridge bracket buries the fan and its screw. Prepared walkthrough of the full workflow.',
    occurrences: 12,
    revision: 'Rev A',
    status: 'ready',
    provenance: 'illustrative',
    updated_at: '2026-10-27',
  },
  {
    id: 'prj_b01',
    fixture_code: 'B01',
    name: 'Enclosure service cartridge',
    description: 'Directly reachable cartridge. Confirms no unnecessary edit is proposed.',
    occurrences: null,
    revision: null,
    status: 'not_authored',
    provenance: 'illustrative',
    updated_at: null,
  },
  {
    id: 'prj_b03',
    fixture_code: 'B03',
    name: 'Tool access conflict',
    description: 'A driver route is blocked. Web offset competes with relief and a keep-out.',
    occurrences: null,
    revision: null,
    status: 'not_authored',
    provenance: 'illustrative',
    updated_at: null,
  },
]
