import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls, Grid } from '@react-three/drei'
import { useEffect, useMemo, useRef, useState, type Dispatch, type MutableRefObject } from 'react'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import * as THREE from 'three'
import { api } from '@/api'
import type { PlanResult, PreviewMesh, Revision, RunRecord, Vec3 } from '@/domain/types'
import { hasWebGL } from '@/three/units'
import { selectedCandidate, type Action, type WorkspaceState } from './model'

interface Props { revision: Revision; run: RunRecord | null; state: WorkspaceState; dispatch: Dispatch<Action> }
type Link = { camera: THREE.Camera; controls: OrbitControlsImpl; invalidate: () => void }

function usePreview(id?: string | null) {
  const [data, setData] = useState<{ id: string; mesh: PreviewMesh } | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!id) return
    const controller = new AbortController()
    setError(null)
    fetch(api.artifactUrl(id), { signal: controller.signal }).then(async (r) => {
      if (!r.ok) throw new Error('The CAD preview artifact could not be loaded.')
      const mesh = await r.json() as PreviewMesh
      if (mesh.units !== 'm' || !mesh.scale_already_applied) throw new Error('Unexpected preview units; rendering stopped.')
      setData({ id, mesh })
    }).catch((e: Error) => { if (!controller.signal.aborted) setError(e.message) })
    return () => controller.abort()
  }, [id])
  return { mesh: data && data.id === id ? data.mesh : null, error }
}

function offsetsFor(plan: PlanResult | null | undefined, position: number) {
  const offsets: Record<string, Vec3> = {}
  if (!plan || plan.status !== 'feasible') return offsets
  plan.steps.forEach((step, i) => {
    if (!step.certificate_ids.length) return
    const f = Math.max(0, Math.min(1, position - i))
    offsets[step.component_id] = step.start_mm.map((v, j) => (v + (step.end_mm[j] - v) * f) * 0.001) as Vec3
  })
  return offsets
}

function Part({ component, color, opacity, offset, visible, dispatch }: { component: PreviewMesh['components'][number]; color: string; opacity: number; offset: Vec3; visible: boolean; dispatch: Dispatch<Action> }) {
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.Float32BufferAttribute(component.vertices_m.flat(), 3))
    g.setIndex(component.triangles.flat())
    g.computeVertexNormals()
    return g
  }, [component])
  useEffect(() => () => geometry.dispose(), [geometry])
  // e.delta is the pointer travel in px since pointerdown: a drag orbits the camera
  // and must not also select whatever part the pointer happens to be released over.
  return <mesh geometry={geometry} visible={visible} position={offset} onClick={(e) => { e.stopPropagation(); if (e.delta > 4) return; dispatch({ type: 'select', id: component.occurrence_id }) }} onPointerOver={(e) => { e.stopPropagation(); dispatch({ type: 'hover', id: component.occurrence_id }) }} onPointerOut={() => dispatch({ type: 'hover', id: null })}>
    <meshStandardMaterial color={color} metalness={0.35} roughness={0.45} transparent={opacity < 1} opacity={opacity} depthWrite={opacity >= 1} />
  </mesh>
}

/**
 * Keeps the whole assembly in view for this canvas's aspect ratio. Narrow views
 * (the side-by-side comparison on a laptop) need more distance than the default
 * framing; the camera only ever moves further out, keeps its viewing direction,
 * and the fitted pose becomes what Reset returns to.
 */
function FitCamera({ radius }: { radius: number }) {
  const { camera, size, controls, invalidate } = useThree()
  useEffect(() => {
    if (!(camera instanceof THREE.PerspectiveCamera) || !size.width || !size.height || !radius) return
    const vertical = THREE.MathUtils.degToRad(camera.fov)
    const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * (size.width / size.height))
    const needed = (radius * 1.08) / Math.sin(Math.min(vertical, horizontal) / 2)
    const orbit = controls as unknown as OrbitControlsImpl | null
    const target = orbit?.target ?? new THREE.Vector3()
    const offset = camera.position.clone().sub(target)
    if (offset.length() < needed) {
      camera.position.copy(target).add(offset.setLength(needed))
      camera.updateProjectionMatrix()
      orbit?.update()
    }
    orbit?.saveState()
    invalidate()
  }, [camera, controls, invalidate, radius, size.width, size.height])
  return null
}

function SyncControls({ links, index, busy }: { links: MutableRefObject<Array<Link | null>>; index: number; busy: MutableRefObject<boolean> }) {
  const { camera, invalidate } = useThree()
  const ref = useRef<OrbitControlsImpl>(null)
  useEffect(() => {
    if (ref.current) links.current[index] = { camera, controls: ref.current, invalidate }
    return () => { links.current[index] = null }
  }, [camera, index, invalidate, links])
  return <OrbitControls ref={ref} makeDefault enableDamping={false} onChange={() => {
    invalidate()
    const peer = links.current[index === 0 ? 1 : 0]
    if (busy.current || !peer || !ref.current) return
    busy.current = true
    peer.camera.position.copy(camera.position)
    peer.camera.quaternion.copy(camera.quaternion)
    peer.controls.target.copy(ref.current.target)
    peer.controls.update()
    peer.invalidate()
    busy.current = false
  }} />
}

export function LiveViewport({ revision, run, state, dispatch }: Props) {
  const original = usePreview(revision.preview_artifact_id)
  const candidate = selectedCandidate(run, state)
  const revised = usePreview(candidate?.preview_artifact_id)
  const compare = state.mode === 'compare'
  const showRevised = ['redesign', 'compare', 'export'].includes(state.mode) && !!candidate
  const [position, setPosition] = useState(0)
  const links = useRef<Array<Link | null>>([null, null])
  const syncing = useRef(false)
  const webgl = useMemo(hasWebGL, [])
  const plan = showRevised ? candidate?.revised_plan : run?.baseline
  useEffect(() => setPosition(0), [state.target, state.candidateId, state.mode])
  const camera = useMemo(() => {
    const e = revision.manifest.envelope_mm
    const size = Math.max(...e.max.map((x, i) => x - e.min[i])) * 0.001
    return [size * 1.8, size * 1.4, size * 1.8] as Vec3
  }, [revision])
  // Bounding-sphere radius of the actual tessellated parts about the orbit target
  // (the origin), in metres. The declared design envelope is far larger than the
  // parts and would make every view needlessly distant.
  const radius = useMemo(() => {
    let r = 0
    for (const c of original.mesh?.components ?? []) for (const v of c.vertices_m) r = Math.max(r, Math.hypot(v[0], v[1], v[2]))
    return r
  }, [original.mesh])

  const draw = (mesh: PreviewMesh | null, index: number, revisedSide: boolean) => {
    if (!mesh) return <p className="panel__empty">Loading actual CAD tessellation…</p>
    const offsets = offsetsFor(revisedSide ? candidate?.revised_plan : run?.baseline, position)
    const witness = state.mode === 'analyze' ? run?.baseline?.rejections.find((r) => r.id === state.witness) : null
    if (witness && witness.action_kind !== 'TOOL_APPROACH' && witness.witness_travel_mm !== null) {
      const axis = 'XYZ'.indexOf(witness.axis[0])
      const off: Vec3 = [0, 0, 0]
      off[axis] = witness.witness_travel_mm * (witness.axis[1] === '+' ? 1 : -1) * 0.001
      offsets[witness.component_id] = off
    }
    return <Canvas frameloop="demand" camera={{ position: camera, fov: 35, near: 0.001, far: 10 }} dpr={[1, 1.5]} onPointerMissed={() => dispatch({ type: 'select', id: null })}>
      <color attach="background" args={['#eceeea']} />
      <ambientLight intensity={1.6} /><directionalLight position={[1, 2, 1]} intensity={3} />
      <group rotation={[-Math.PI / 2, 0, 0]}>
        {mesh.components.map((c) => {
          const id = c.occurrence_id
          const selected = state.selected === id || state.hovered === id
          const color = witness?.obstacle_ids.includes(id) ? '#c78a28' : selected ? '#63a3c0' : state.target === id ? '#4287b4' : revisedSide && candidate?.diff?.changed_component_id === id ? candidate.state === 'checked' ? '#6a9b7a' : '#6b9baf' : '#aeb5b6'
          return <Part key={id} component={c} color={color} opacity={state.xray && state.target !== id ? 1 - state.xray * 0.85 : 1} offset={offsets[id] ?? [0, 0, 0]} visible={!state.hidden.includes(id) && !witness?.removed_ids?.includes(id) && (!state.isolated || state.isolated === id)} dispatch={dispatch} />
        })}
      </group>
      <Grid args={[1, 1]} cellSize={0.01} sectionSize={0.05} fadeDistance={1.5} position={[0, -0.015, 0]} />
      <SyncControls index={index} links={links} busy={syncing} />
      <FitCamera radius={radius} />
    </Canvas>
  }

  return <div className={`vp ${compare ? 'vp--compare' : ''}`} data-geometry-source="backend-brep" data-preview-id={showRevised && !compare ? candidate?.preview_artifact_id : revision.preview_artifact_id}>
    <div className="vp__views">
      <div className="vp__view">
        <div className="vp__label"><strong>{compare || !showRevised ? 'Original' : 'Constructed candidate'}</strong><span>{revision.label}</span></div>
        {!webgl ? <p className="panel__empty">WebGL is unavailable. Component selection, measurements, checks and CAD downloads remain available.</p> : draw(showRevised && !compare ? revised.mesh : original.mesh, 0, showRevised && !compare)}
      </div>
      {compare && <div className="vp__view"><div className="vp__label"><strong>Revised</strong><span>{candidate?.proposal.template_id} · actual constructed geometry</span></div>{webgl && draw(revised.mesh, 1, true)}</div>}
    </div>
    <div className="vp__tools" role="toolbar" aria-label="View controls">
      <button type="button" onClick={() => { links.current.forEach((l) => { if (l) { l.controls.reset(); l.invalidate() } }); setPosition(0) }}>Reset</button>
      <button type="button" onClick={() => dispatch({ type: 'showAll' })}>Show all</button>
      <label className="vp__slider">Transparency <input type="range" min="0" max="1" step="0.05" value={state.xray} onChange={(e) => dispatch({ type: 'xray', value: Number(e.target.value) })} /></label>
      {plan?.status === 'feasible' && <label className="vp__slider">Checked route <input aria-label="Checked route position" type="range" min="0" max={plan.steps.length} step="0.01" value={position} onChange={(e) => { dispatch({ type: 'witness', id: null }); setPosition(Number(e.target.value)) }} /></label>}
    </div>
    <p className="vp__frame mono">Actual BRep tessellation · {original.mesh?.triangle_count ?? '…'} triangles · mm, Z up · presentation only</p>
    {(original.error || (showRevised && revised.error)) && <p role="alert">{original.error ?? revised.error}</p>}
  </div>
}
