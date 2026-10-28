import { useFrame, type ThreeEvent } from '@react-three/fiber'
import { useMemo, useRef, type ReactNode } from 'react'
import * as THREE from 'three'
import type { BracketParameters, Vec3 } from '@/domain/types'
import { b02Manifest } from '@/fixtures/b02'
import { BASIS, MATERIALS, box, cylY, cylZ, plate, unitSolid, type Mat, type Solid } from './primitives'
import { CAD_ROTATION, MM } from './units'

/* ── part registry ──────────────────────────────────────────────────────── */

export const PART_IDS = [
  'chassis',
  'cover',
  'screw_c1',
  'screw_c2',
  'screw_c3',
  'screw_c4',
  'bridge_bracket',
  'screw_b1',
  'screw_b2',
  'fan_module',
  'screw_f1',
  'pcb_controller',
] as const
export type PartId = (typeof PART_IDS)[number]
export const isPartId = (id: string): id is PartId => (PART_IDS as readonly string[]).includes(id)

export type PartTone = 'default' | 'target' | 'selected' | 'obstruction' | 'protected'

export interface PartView {
  visible: boolean
  opacity: number
  tone: PartTone
  /** displacement from the assembled pose, world mm */
  offset: Vec3
  hover: boolean
  /** per-finish opacity multiplier, e.g. see-through aluminium walls over a solid base */
  fade?: Partial<Record<Mat, number>>
}

export interface Relief {
  cx: number
  cy: number
  w: number
  d: number
}

/**
 * Mutable view state read every rendered frame. Mutate it and call invalidate();
 * no React re-render is needed for animation.
 */
export interface AssemblyView {
  parts: Record<PartId, PartView>
  relief: Relief | null
  /** ghost of the target envelope used for sweep illustrations */
  probe: { z: number; opacity: number; tone: 'target' | 'obstruction' } | null
  /** straight driver approach volume over the fan screw; z is the tip height in mm */
  tool: { tip: number; opacity: number; blocked: boolean } | null
  theme: 'light' | 'dark'
}

export function createView(theme: 'light' | 'dark' = 'light'): AssemblyView {
  const parts = {} as Record<PartId, PartView>
  for (const id of PART_IDS) parts[id] = { visible: true, opacity: 1, tone: 'default', offset: [0, 0, 0], hover: false }
  return { parts, relief: null, probe: null, tool: null, theme }
}

/* ── geometry (CAD mm, Z up) ────────────────────────────────────────────── */

const WEB_KEYS = ['web_front', 'web_back', 'web_left', 'web_right'] as const

function buildParts(p: BracketParameters): Record<PartId, Solid[]> {
  const half = p.span_mm / 2
  const footIn = half - p.foot_width_mm / 2
  const footOut = half + p.foot_width_mm / 2
  const fz0 = 4
  const fz1 = fz0 + p.foot_thickness_mm
  const webZ0 = fz0 + p.web_underside_height_mm

  const coverScrew = (x: number, y: number): Solid[] => [cylZ(x, y, 61, 63, 2.8, 'oxide'), cylZ(x, y, 51, 61, 1.5, 'oxide', 14)]

  const blades: Solid[] = Array.from({ length: 7 }, (_, i) => {
    const g = new THREE.BoxGeometry(7.6, 0.8, 5.2)
    g.rotateX(0.62)
    g.translate(9.5, 0, 0)
    g.rotateY((i / 7) * Math.PI * 2)
    g.translate(0, -20, 21)
    return { geometry: g, edges: new THREE.EdgesGeometry(g, 28), mat: 'plastic' as Mat }
  })

  return {
    chassis: [
      box([-80, -55, 0], [80, 55, 4], 'anodized'),
      ...[-66, 66].flatMap((x) => [-41, 41].map((y) => cylZ(x, y, -2, 0, 6, 'rubber'))),
      plate(
        [-80, 4, 80, 58],
        Array.from({ length: 6 }, (_, i) => ({ rect: [-16, 11 + i * 4, 16, 13.2 + i * 4] as [number, number, number, number] })),
        3,
        BASIS.xzFront,
        [0, -52, 0],
        'aluminum',
      ),
      box([-80, 52, 4], [80, 55, 58], 'aluminum'),
      plate([-52, 4, 52, 58], [{ rect: [24, 12, 36, 20] }], 3, BASIS.yzSide, [-80, 0, 0], 'aluminum'),
      box([77, -52, 4], [80, 52, 58], 'aluminum'),
      ...[-72, 72].flatMap((x) => [-47, 47].map((y) => cylZ(x, y, 4, 58, 5, 'aluminum'))),
      box([-17, -28, 4], [17, -12, 6], 'anodized'),
      ...[
        [-71, 19],
        [-27, 19],
        [-71, 45],
        [-27, 45],
      ].map(([x, y]) => cylZ(x, y, 4, 10, 2.2, 'steel', 16)),
    ],
    cover: [
      plate(
        [-80, -55, 80, 55],
        [
          [-72, -47],
          [72, -47],
          [-72, 47],
          [72, 47],
        ].map(([x, y]) => ({ circle: [x, y, 1.8] as [number, number, number] })),
        3,
        BASIS.xyUp,
        [0, 0, 58],
        'aluminum',
        0.6,
      ),
    ],
    screw_c1: coverScrew(-72, -47),
    screw_c2: coverScrew(72, -47),
    screw_c3: coverScrew(-72, 47),
    screw_c4: coverScrew(72, 47),
    bridge_bracket: [
      ...[-1, 1].map((s) =>
        plate(
          s > 0 ? [footIn, -p.foot_depth_mm / 2, footOut, p.foot_depth_mm / 2] : [-footOut, -p.foot_depth_mm / 2, -footIn, p.foot_depth_mm / 2],
          [{ circle: [s * half, 0, p.hole_diameter_mm / 2] }],
          p.foot_thickness_mm,
          BASIS.xyUp,
          [0, 0, fz0],
          'steel',
        ),
      ),
      ...[-1, 1].map((s) =>
        box(
          s > 0 ? [footIn, -p.post_depth_mm / 2, fz1] : [-footIn - p.post_width_mm, -p.post_depth_mm / 2, fz1],
          s > 0 ? [footIn + p.post_width_mm, p.post_depth_mm / 2, webZ0] : [-footIn, p.post_depth_mm / 2, webZ0],
          'steel',
        ),
      ),
      ...WEB_KEYS.map((k) => unitSolid('steel', k)),
    ],
    screw_b1: [cylZ(-half, 0, fz1, fz1 + 2.5, 3, 'oxide'), cylZ(-half, 0, 0, fz1, 1.5, 'oxide', 14)],
    screw_b2: [cylZ(half, 0, fz1, fz1 + 2.5, 3, 'oxide'), cylZ(half, 0, 0, fz1, 1.5, 'oxide', 14)],
    fan_module: [
      plate(
        [-15, 6, 15, 36],
        [
          { circle: [0, 21, 13.6] },
          ...[
            [-12, 9],
            [12, 9],
            [-12, 33],
            [12, 33],
          ].map(([u, v]) => ({ circle: [u, v, 1.6] as [number, number, number] })),
        ],
        12,
        BASIS.xzFront,
        [0, -14, 0],
        'plastic',
      ),
      cylY(0, 21, -24.5, -15.5, 5.5, 'plastic'),
      ...blades,
      box([15, -26, 6], [27, -14, 8], 'plastic'),
    ],
    screw_f1: [cylZ(21, -20, 8, 10.5, 2.8, 'oxide'), cylZ(21, -20, 2, 8, 1.5, 'oxide', 14)],
    pcb_controller: [
      box([-74, 16, 10], [-24, 48, 11.6], 'board'),
      box([-60, 24, 11.6], [-48, 36, 13], 'chip'),
      box([-44, 30, 11.6], [-36, 40, 12.6], 'chip'),
      box([-74, 26, 11.6], [-66, 34, 18], 'connector'),
      cylZ(-31, 22, 11.6, 19, 3, 'cap'),
      cylZ(-31, 42, 11.6, 17, 2.5, 'cap'),
    ],
  }
}

/** Web pieces around a T01 opening; bracket constructor v1 web bounds. */
function webBoxes(p: BracketParameters, relief: Relief | null): Record<(typeof WEB_KEYS)[number], [Vec3, Vec3] | null> {
  const x0 = -p.web_length_mm / 2
  const x1 = p.web_length_mm / 2
  const y0 = -p.web_depth_mm / 2
  const y1 = p.web_depth_mm / 2
  const z0 = 4 + p.web_underside_height_mm
  const z1 = z0 + p.web_thickness_mm
  if (!relief || relief.w < 0.05 || relief.d < 0.05) {
    return { web_front: [[x0, y0, z0], [x1, y1, z1]], web_back: null, web_left: null, web_right: null }
  }
  const rx0 = relief.cx - relief.w / 2
  const rx1 = relief.cx + relief.w / 2
  const ry0 = relief.cy - relief.d / 2
  const ry1 = relief.cy + relief.d / 2
  return {
    web_front: [[x0, y0, z0], [x1, ry0, z1]],
    web_back: [[x0, ry1, z0], [x1, y1, z1]],
    web_left: [[x0, ry0, z0], [rx0, ry1, z1]],
    web_right: [[rx1, ry0, z0], [x1, ry1, z1]],
  }
}

/* ── tones ──────────────────────────────────────────────────────────────── */

const TONE = {
  target: new THREE.Color('#3268f5'),
  selected: new THREE.Color('#3268f5'),
  obstruction: new THREE.Color('#e4602f'),
  protected: new THREE.Color('#6e7378'),
}
const EDGE = {
  light: new THREE.Color('#17191b'),
  dark: new THREE.Color('#e9e8e3'),
  target: new THREE.Color('#1b3a9a'),
  obstruction: new THREE.Color('#7a2a0e'),
}
const HOVER = new THREE.Color('#3268f5')

interface Registered {
  id: PartId
  group: THREE.Group
  mats: Array<{ m: THREE.MeshStandardMaterial; spec: (typeof MATERIALS)[Mat]; key: Mat }>
  edge: THREE.LineBasicMaterial
  lines: THREE.LineSegments[]
  web: Partial<Record<string, { mesh: THREE.Mesh; lines: THREE.LineSegments }>>
}

const noRaycast = () => null

/* ── components ─────────────────────────────────────────────────────────── */

export function CadSpace({ children }: { children: ReactNode }) {
  return (
    <group rotation={CAD_ROTATION} scale={MM}>
      {children}
    </group>
  )
}

interface AssemblyProps {
  view: React.MutableRefObject<AssemblyView>
  interactive?: boolean
  onSelect?: (id: PartId) => void
  onHover?: (id: PartId | null) => void
  params?: BracketParameters
}

export function ModuleAssembly({ view, interactive = false, onSelect, onHover, params }: AssemblyProps) {
  const p = params ?? b02Manifest.template_bindings[0].parameters
  const parts = useMemo(() => buildParts(p), [p])
  const registry = useRef(new Map<PartId, Registered>())
  const probeRef = useRef<THREE.Group>(null)
  const probeMat = useMemo(() => new THREE.MeshStandardMaterial({ transparent: true, depthWrite: false, roughness: 0.4, side: THREE.DoubleSide }), [])
  const toolRef = useRef<THREE.Group>(null)
  const toolMat = useMemo(() => new THREE.MeshStandardMaterial({ transparent: true, depthWrite: false, roughness: 0.5 }), [])

  useFrame(() => {
    const v = view.current
    const dark = v.theme === 'dark'
    for (const r of registry.current.values()) {
      const s = v.parts[r.id]
      r.group.visible = s.visible && s.opacity > 0.004
      r.group.position.set(s.offset[0], s.offset[1], s.offset[2])
      for (const { m, spec, key } of r.mats) {
        const opacity = s.opacity * (s.fade?.[key] ?? 1)
        m.color.set(spec.color)
        m.metalness = spec.metalness
        m.roughness = spec.roughness
        m.emissive.setRGB(0, 0, 0)
        if (s.tone !== 'default') {
          const t = TONE[s.tone]
          if (s.tone === 'protected') m.color.lerp(t, 0.35)
          else {
            m.color.copy(t)
            m.metalness = Math.min(spec.metalness, 0.25)
            m.roughness = 0.42
            m.emissive.copy(t).multiplyScalar(dark ? 0.32 : s.tone === 'selected' ? 0.2 : 0.12)
          }
        }
        if (s.hover && s.tone !== 'selected') m.color.lerp(HOVER, 0.14)
        m.opacity = opacity
        const transparent = opacity < 0.995
        // `transparent` is compiled into the program (OPAQUE define): recompile on change
        if (m.transparent !== transparent) {
          m.transparent = transparent
          m.needsUpdate = true
        }
        m.depthWrite = opacity > 0.55
      }
      const edgeColor = s.tone === 'target' || s.tone === 'selected' ? EDGE.target : s.tone === 'obstruction' ? EDGE.obstruction : dark ? EDGE.dark : EDGE.light
      r.edge.color.copy(edgeColor)
      const strong = s.tone === 'selected' || s.tone === 'obstruction'
      // highlighted parts keep their outline visible through occluding parts, as in CAD selection
      const xray = s.tone === 'selected' || s.tone === 'target' || s.tone === 'obstruction'
      r.edge.depthTest = !xray
      for (const l of r.lines) l.renderOrder = xray ? 10 : 0
      r.edge.opacity = (strong ? 0.75 : xray ? 0.6 : dark ? 0.2 : 0.3) * Math.min(1, s.opacity * 1.6)

      if (r.id === 'bridge_bracket') {
        const boxes = webBoxes(p, v.relief)
        for (const k of WEB_KEYS) {
          const piece = r.web[k]
          const b = boxes[k]
          if (!piece) continue
          const ok = !!b && b[1][0] - b[0][0] > 0.01 && b[1][1] - b[0][1] > 0.01
          piece.mesh.visible = ok
          if (ok && b) {
            piece.mesh.position.set((b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2, (b[0][2] + b[1][2]) / 2)
            piece.mesh.scale.set(b[1][0] - b[0][0], b[1][1] - b[0][1], b[1][2] - b[0][2])
          }
        }
      }
    }

    if (probeRef.current) {
      const pr = v.probe
      probeRef.current.visible = !!pr && pr.opacity > 0.01
      if (pr) {
        probeRef.current.position.z = pr.z
        probeMat.color.copy(pr.tone === 'obstruction' ? TONE.obstruction : TONE.target)
        probeMat.emissive.copy(probeMat.color).multiplyScalar(0.35)
        probeMat.opacity = pr.opacity
      }
    }
    if (toolRef.current) {
      const t = v.tool
      toolRef.current.visible = !!t && t.opacity > 0.01
      if (t) {
        toolRef.current.position.z = t.tip
        toolMat.color.copy(t.blocked ? TONE.obstruction : TONE.target)
        toolMat.emissive.copy(toolMat.color).multiplyScalar(0.3)
        toolMat.opacity = t.opacity
      }
    }
  })

  const register = (id: PartId) => (group: THREE.Group | null) => {
    if (!group) {
      registry.current.delete(id)
      return
    }
    const mats: Registered['mats'] = []
    const seen = new Set<THREE.Material>()
    let edge: THREE.LineBasicMaterial | null = null
    const lines: THREE.LineSegments[] = []
    const web: Registered['web'] = {}
    group.traverse((o) => {
      if (o instanceof THREE.Mesh && !seen.has(o.material as THREE.Material)) {
        seen.add(o.material as THREE.Material)
        mats.push({ m: o.material as THREE.MeshStandardMaterial, spec: MATERIALS[o.userData.mat as Mat], key: o.userData.mat as Mat })
      }
      if (o instanceof THREE.LineSegments) {
        edge = o.material as THREE.LineBasicMaterial
        lines.push(o)
      }
      if (o instanceof THREE.Mesh && o.userData.key) {
        const lines = o.children.find((c) => c instanceof THREE.LineSegments) as THREE.LineSegments
        web[o.userData.key as string] = { mesh: o, lines }
      }
    })
    registry.current.set(id, { id, group, mats, edge: edge!, lines, web })
  }

  return (
    <CadSpace>
      {PART_IDS.map((id) => (
        <PartGroup key={id} id={id} solids={parts[id]} groupRef={register(id)} interactive={interactive} onSelect={onSelect} onHover={onHover} />
      ))}
      {/* sweep probe: target envelope, illustration only */}
      <group ref={probeRef} visible={false}>
        <mesh material={probeMat} raycast={noRaycast} position={[0, -20, 21]}>
          <boxGeometry args={[30, 12, 30]} />
        </mesh>
      </group>
      {/* straight driver approach volume over screw_f1 (driver_ph1: shaft r3 × 80, handle r14 × 100) */}
      <group ref={toolRef} visible={false}>
        <mesh material={toolMat} raycast={noRaycast} position={[21, -20, 40]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[3, 3, 80, 24]} />
        </mesh>
        <mesh material={toolMat} raycast={noRaycast} position={[21, -20, 130]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[14, 14, 100, 32]} />
        </mesh>
      </group>
    </CadSpace>
  )
}

function PartGroup({
  id,
  solids,
  groupRef,
  interactive,
  onSelect,
  onHover,
}: {
  id: PartId
  solids: Solid[]
  groupRef: (g: THREE.Group | null) => void
  interactive: boolean
  onSelect?: (id: PartId) => void
  onHover?: (id: PartId | null) => void
}) {
  // one material per (part, finish) so tone and opacity are independent per part
  const mats = useMemo(() => {
    const m = new Map<Mat, THREE.MeshStandardMaterial>()
    for (const s of solids) {
      if (!m.has(s.mat)) {
        const spec = MATERIALS[s.mat]
        m.set(s.mat, new THREE.MeshStandardMaterial({ color: spec.color, metalness: spec.metalness, roughness: spec.roughness, envMapIntensity: 1.1 }))
      }
    }
    return m
  }, [solids])
  const edgeMat = useMemo(() => new THREE.LineBasicMaterial({ color: '#17191b', transparent: true, opacity: 0.3 }), [])

  const handlers = interactive
    ? {
        onClick: (e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation()
          onSelect?.(id)
        },
        onPointerOver: (e: ThreeEvent<PointerEvent>) => {
          e.stopPropagation()
          onHover?.(id)
          document.body.style.cursor = 'pointer'
        },
        onPointerOut: () => {
          onHover?.(null)
          document.body.style.cursor = ''
        },
      }
    : {}

  return (
    <group ref={groupRef} name={id} {...handlers}>
      {solids.map((s, i) => (
        <mesh key={i} geometry={s.geometry} material={mats.get(s.mat)} userData={{ mat: s.mat, key: s.key }} castShadow receiveShadow>
          <lineSegments geometry={s.edges} material={edgeMat} raycast={noRaycast} />
        </mesh>
      ))}
    </group>
  )
}
