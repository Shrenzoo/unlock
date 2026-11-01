// Real data exported by scripts/export_data.py; nothing here is hand-made.
import b05Json from '../public/data/b05.json'
import galleryJson from '../public/data/gallery.json'
import liveJson from '../public/data/live_run.json'

export type Mesh = { vertices: number[]; indices: number[] }
export type Component = Mesh & { id: string; label: string; role: string }

export type LiveEvent =
  | { t: number; kind: 'baseline'; status: string }
  | { t: number; kind: 'turn'; turn: number; note: string }
  | {
      t: number
      kind: 'tool'
      turn: number
      tool: string
      status: string
      parameters?: Record<string, number>
      evidence_ids?: string[]
      rationale?: string
    }
  | { t: number; kind: 'final'; outcome: string }

export const b05 = b05Json as unknown as {
  components: Component[]
  revised_bridge: Mesh
  candidate: { template: string; parameters: Record<string, number>; geometry_hash: string }
  witness: { point_mm: [number, number, number]; travel_mm: number; component_ids: string[] }
  removal: { component_id: string; axis: string; distance_mm: number }
}

export const live = liveJson as unknown as {
  run_id: string
  model: string
  generated_at: string
  total_s: number
  tool_calls: number
  rejected_calls: number
  turns: number
  input_tokens: number
  output_tokens: number
  tools: string[]
  tools_used: string[]
  stages: { stage: string; at_s: number; detail: string }[]
  checks: { id: string; result: string }[]
  changed_volume_mm3: number
  plan_steps: { kind: string; component_id: string; axis: string; distance_mm: number }[]
  replay: string
  reverse: string
  events: LiveEvent[]
}

export const gallery = galleryJson as {
  code: string
  name: string
  description?: string
  outcome: string
}[]

export const stageAt = (stage: string) => live.stages.find((s) => s.stage === stage)!.at_s
