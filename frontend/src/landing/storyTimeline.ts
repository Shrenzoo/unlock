import type { AssemblyView } from '@/three/ModuleAssembly'
import { B02_RELIEF } from '@/fixtures/b02'

/**
 * Scroll story for the landing page. Pure mapping from progress (0..1) to the
 * assembly view and camera, so the same frame always looks the same whichever
 * direction the reader scrolls. Illustrative: these poses are hand-placed, not
 * stored plan transforms.
 */

export const SCENES = [
  { id: 'product', label: 'Product', start: 0 },
  { id: 'failed', label: 'Failed part', start: 0.16 },
  { id: 'obstruction', label: 'Obstruction', start: 0.34 },
  { id: 'redesign', label: 'Redesign', start: 0.56 },
  { id: 'path', label: 'Accessible path', start: 0.76 },
] as const

export function sceneAt(p: number) {
  let i = 0
  for (let k = 0; k < SCENES.length; k++) if (p >= SCENES[k].start - 0.02) i = k
  return i
}

const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
/** progress of p through [a, b], eased in-out */
const seg = (p: number, a: number, b: number) => {
  const t = clamp01((p - a) / (b - a))
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
}
const lin = (p: number, a: number, b: number) => clamp01((p - a) / (b - a))
const mix = (a: number, b: number, t: number) => a + (b - a) * t

type V3 = [number, number, number]
const CAMERA_KEYS: Array<{ p: number; pos: V3; target: V3 }> = [
  { p: 0.0, pos: [4.35, 2.34, 5.4], target: [0, 0.28, 0] },
  { p: 0.16, pos: [3.45, 2.18, 4.58], target: [0, 0.3, 0] },
  { p: 0.34, pos: [2.0, 1.66, 2.87], target: [0.06, 0.28, 0.12] },
  { p: 0.56, pos: [1.85, 1.06, 2.36], target: [0.06, 0.34, 0.14] },
  { p: 0.76, pos: [1.27, 2.45, 1.87], target: [0.02, 0.36, 0.16] },
  { p: 0.95, pos: [2.6, 1.95, 3.85], target: [0.02, 0.6, 0.1] },
  { p: 1.0, pos: [2.6, 1.95, 3.85], target: [0.02, 0.6, 0.1] },
]

export function cameraAt(p: number): { pos: V3; target: V3 } {
  let i = 0
  while (i < CAMERA_KEYS.length - 2 && p > CAMERA_KEYS[i + 1].p) i++
  const a = CAMERA_KEYS[i]
  const b = CAMERA_KEYS[i + 1]
  const t = seg(p, a.p, b.p)
  return {
    pos: [mix(a.pos[0], b.pos[0], t), mix(a.pos[1], b.pos[1], t), mix(a.pos[2], b.pos[2], t)],
    target: [mix(a.target[0], b.target[0], t), mix(a.target[1], b.target[1], t), mix(a.target[2], b.target[2], t)],
  }
}

const COVER_SCREWS = ['screw_c1', 'screw_c2', 'screw_c3', 'screw_c4'] as const

export function applyStory(p: number, v: AssemblyView) {
  // reset to the assembled, neutral state, then layer each scene on top
  for (const s of Object.values(v.parts)) {
    s.visible = true
    s.opacity = 1
    s.tone = 'default'
    s.offset[0] = 0
    s.offset[1] = 0
    s.offset[2] = 0
    s.hover = false
  }
  v.relief = null
  v.probe = null
  v.tool = null

  // Scene 2 — open the product, reveal the target
  const lift = seg(p, 0.17, 0.3)
  for (const id of COVER_SCREWS) {
    v.parts[id].offset[2] = mix(0, 90, lift)
    v.parts[id].opacity = 1 - lin(p, 0.22, 0.3)
  }
  v.parts.cover.offset[2] = mix(0, 70, seg(p, 0.19, 0.31))
  v.parts.cover.opacity = 1 - lin(p, 0.24, 0.32)
  v.parts.chassis.opacity = mix(1, 0.16, seg(p, 0.2, 0.32))
  v.parts.pcb_controller.opacity = mix(1, 0.35, seg(p, 0.2, 0.32))
  if (p > 0.2) v.parts.fan_module.tone = 'target'

  // Scene 3 — attempt the straight lift, meet the web
  if (p >= 0.34 && p < 0.58) {
    const rise = seg(p, 0.35, 0.41)
    const fade = 1 - lin(p, 0.54, 0.58)
    v.probe = { z: mix(0, 2, rise), opacity: 0.42 * fade, tone: p > 0.405 ? 'obstruction' : 'target' }
    if (p > 0.405) v.parts.bridge_bracket.tone = 'obstruction'
    const drop = seg(p, 0.44, 0.51)
    v.tool = { tip: mix(150, 42, drop), opacity: 0.38 * fade * lin(p, 0.43, 0.45), blocked: p > 0.505 }
  }

  // Scene 4 — T01 relief through the web; protected regions stay put
  if (p >= 0.56) {
    const grow = seg(p, 0.6, 0.71)
    v.relief = { cx: B02_RELIEF.center_x_mm, cy: B02_RELIEF.center_y_mm, w: B02_RELIEF.width_mm * grow, d: B02_RELIEF.depth_mm * grow }
  }

  // Scene 5 — screw out, then the fan lifts through the relief
  if (p >= 0.76) {
    v.parts.screw_f1.offset[2] = mix(0, 52, seg(p, 0.77, 0.83))
    v.parts.screw_f1.opacity = 1 - lin(p, 0.86, 0.9)
    v.parts.fan_module.offset[2] = mix(0, 64, seg(p, 0.83, 0.94))
  }
}
