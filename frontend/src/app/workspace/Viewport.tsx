import { Canvas, useThree } from '@react-three/fiber'
import { CameraControls, Grid } from '@react-three/drei'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type Dispatch, type MutableRefObject } from 'react'
import * as THREE from 'three'
import type { GeometryDiff, RunRecord, Vec3 } from '@/domain/types'
import { b02Manifest } from '@/fixtures/b02'
import { CadSpace, ModuleAssembly, createView, type PartId, type Relief } from '@/three/ModuleAssembly'
import { Studio } from '@/three/Studio'
import { FallbackDrawing } from '@/three/FallbackDrawing'
import { MM, hasWebGL, prefersReducedMotion } from '@/three/units'
import { Glyph } from '@/ui/Evidence'
import { applyWitness, composeView, poseAt, reliefFor, segmentsFor, selectedCandidate, type Action, type Pose, type Segment, type WorkspaceState } from './model'

const HOME = { pos: [2.45, 3.15, 3.35] as Vec3, target: [0, 0.22, 0] as Vec3 }

/** CAD-mm bounds → three.js world box (Z up → Y up, Y → −Z). */
function worldBox(min: Vec3, max: Vec3) {
  return new THREE.Box3(new THREE.Vector3(min[0] * MM, min[2] * MM, -max[1] * MM), new THREE.Vector3(max[0] * MM, max[2] * MM, -min[1] * MM))
}

interface ViewportProps {
  state: WorkspaceState
  dispatch: Dispatch<Action>
  run: RunRecord | null
}

export function Viewport({ state, dispatch, run }: ViewportProps) {
  const webgl = useMemo(hasWebGL, [])
  const reduced = useMemo(prefersReducedMotion, [])
  const controls = useRef<CameraControls | null>(null)
  const controlsB = useRef<CameraControls | null>(null)
  const candidate = selectedCandidate(run, state)
  const compare = state.mode === 'compare'

  // playback is local: re-rendering the whole workspace every frame would be wasteful
  const [playhead, setPlayhead] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)

  const segsOriginal = useMemo(() => (state.baseline.status === 'done' && run?.baseline ? segmentsFor(run.baseline) : []), [run, state.baseline.status])
  const segsRevised = useMemo(() => (candidate?.revised_plan ? segmentsFor(candidate.revised_plan) : []), [candidate])
  const primarySegs = state.mode === 'analyze' ? segsOriginal : state.mode === 'compare' || state.mode === 'export' ? segsRevised : []
  const maxSegs = compare ? Math.max(segsOriginal.length, segsRevised.length) : primarySegs.length

  useEffect(() => {
    setPlayhead(null)
    setPlaying(false)
  }, [state.mode, state.candidateId, state.baseline.status])

  useEffect(() => {
    if (state.witness) {
      setPlayhead(null)
      setPlaying(false)
    }
  }, [state.witness])

  // playback clock
  useEffect(() => {
    if (!playing) return
    let raf = 0
    let last = performance.now()
    const tick = (now: number) => {
      const dt = (now - last) / 1000
      last = now
      setPlayhead((p) => {
        const next = (p ?? 0) + dt * 0.9
        if (next >= maxSegs) {
          setPlaying(false)
          return maxSegs
        }
        return next
      })
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, maxSegs])

  const witnessPose = useMemo<Pose | null>(() => {
    if (!state.witness || !run?.baseline) return null
    const r = run.baseline.rejections.find((x) => x.id === state.witness)
    if (!r) return null
    const pose: Pose = { offsets: {}, done: new Set(), active: null, obstruction: null, tool: null, probe: null }
    // the witness pose is evaluated after the cover is off
    for (const s of run.baseline.steps) pose.offsets[s.component_id as PartId] = s.end_mm
    for (const s of run.baseline.steps) pose.done.add(s.component_id as PartId)
    applyWitness(pose, r, 1)
    return pose
  }, [state.witness, run])

  const relief = state.mode === 'redesign' || state.mode === 'export' ? reliefFor(candidate) : null
  const primaryPose = playhead !== null ? poseAt(primarySegs, playhead) : state.mode === 'analyze' ? witnessPose : null

  const fit = useCallback(
    (which?: string | null) => {
      const comp = which ? b02Manifest.components.find((c) => c.id === which) : null
      const box = comp ? worldBox(comp.bounds_mm.min, comp.bounds_mm.max) : worldBox(b02Manifest.envelope_mm.min, b02Manifest.envelope_mm.max)
      const sphere = box.getBoundingSphere(new THREE.Sphere())
      sphere.radius *= comp ? 1.6 : 1.04
      // fitToSphere keeps the viewing direction; fitToBox would snap to an axis
      for (const c of [controls.current, controlsB.current]) c?.fitToSphere(sphere, !reduced)
    },
    [reduced],
  )
  const reset = useCallback(() => {
    for (const c of [controls.current, controlsB.current]) c?.setLookAt(...HOME.pos, ...HOME.target, !reduced)
  }, [reduced])

  // keyboard: F fit, Home reset, Space play/pause, arrows step
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t.closest('input, textarea, select, [role="tree"]') || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === 'f' || e.key === 'F') fit(state.selected)
      else if (e.key === 'Home') reset()
      else if (maxSegs > 0 && e.key === ' ') {
        e.preventDefault()
        setPlaying((p) => !p)
      } else if (maxSegs > 0 && e.key === ']') setPlayhead((p) => Math.min(maxSegs, Math.floor((p ?? 0) + 1)))
      else if (maxSegs > 0 && e.key === '[') setPlayhead((p) => Math.max(0, Math.ceil((p ?? 0) - 1)))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [fit, reset, maxSegs, state.selected])

  const onSelect = useCallback((id: PartId) => dispatch({ type: 'select', id }), [dispatch])
  const onHover = useCallback((id: PartId | null) => dispatch({ type: 'hover', id }), [dispatch])

  if (!webgl) {
    return (
      <div className="vp vp--fallback" role="img" aria-label="3D view unavailable">
        <FallbackDrawing relief={!!relief} />
        <p>
          WebGL is not available, so the 3D view cannot be shown. The assembly tree, the evidence panel and every result remain available. Analysis does not depend on rendering.
        </p>
      </div>
    )
  }

  const currentSeg: Segment | undefined = playhead !== null ? primarySegs[Math.min(primarySegs.length - 1, Math.floor(playhead))] : undefined

  return (
    <div className={`vp ${compare ? 'vp--compare' : ''}`}>
      <div className="vp__views">
        <div className="vp__view">
          {compare && <ViewLabel title="Original" detail="Rev A, assembled design" />}
          <Canvas frameloop="demand" dpr={[1, 2]} camera={{ fov: 30, position: HOME.pos, near: 0.05, far: 60 }} gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping }} onPointerMissed={() => dispatch({ type: 'select', id: null })}>
            <Scene
              state={state}
              pose={compare ? (playhead !== null ? poseAt(segsOriginal, playhead) : null) : primaryPose}
              relief={compare ? null : relief}
              diff={compare && state.showDiff ? candidate?.diff ?? null : null}
              controls={controls}
              peer={compare ? controlsB : null}
              fitOnMount={compare}
              onSelect={onSelect}
              onHover={onHover}
            />
          </Canvas>
        </div>
        {compare && (
          <div className="vp__view">
            <ViewLabel title="Revised" detail={`Candidate 2, T01 web relief`} />
            <Canvas frameloop="demand" dpr={[1, 2]} camera={{ fov: 30, position: HOME.pos, near: 0.05, far: 60 }} gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping }} onPointerMissed={() => dispatch({ type: 'select', id: null })}>
              <Scene
                state={state}
                pose={playhead !== null ? poseAt(segsRevised, playhead) : null}
                relief={reliefFor(candidate)}
                diff={state.showDiff ? candidate?.diff ?? null : null}
                controls={controlsB}
                peer={controls}
                fitOnMount
                onSelect={onSelect}
                onHover={onHover}
              />
            </Canvas>
          </div>
        )}
      </div>

      <div className="vp__tools" role="toolbar" aria-label="View controls">
        <button type="button" onClick={() => fit(state.selected)} title="Fit to view (F)">
          Fit
        </button>
        <button type="button" onClick={reset} title="Reset camera (Home)">
          Reset
        </button>
        <button type="button" aria-pressed={state.exploded} onClick={() => dispatch({ type: 'explode', value: !state.exploded })} disabled={playhead !== null} title="Display offsets only. Analysis uses the assembled pose.">
          Explode
        </button>
        <label className="vp__slider">
          <span>Transparency</span>
          <input type="range" min={0} max={1} step={0.05} value={state.xray} onChange={(e) => dispatch({ type: 'xray', value: Number(e.target.value) })} aria-valuetext={`${Math.round(state.xray * 100)} percent`} />
        </label>
        {compare && (
          <button type="button" aria-pressed={state.showDiff} onClick={() => dispatch({ type: 'diff', value: !state.showDiff })}>
            Changed region
          </button>
        )}
        {(state.hidden.length > 0 || state.isolated) && (
          <button type="button" onClick={() => dispatch({ type: 'showAll' })}>
            Show all
          </button>
        )}
      </div>

      <p className="vp__frame mono" aria-hidden="true">
        mm, Z up
      </p>

      {maxSegs > 0 && (
        <PlaybackBar
          segs={compare ? (segsRevised.length >= segsOriginal.length ? segsRevised : segsOriginal) : primarySegs}
          total={maxSegs}
          playhead={playhead}
          playing={playing}
          current={currentSeg}
          compare={compare}
          onPlay={() => {
            if (playhead !== null && playhead >= maxSegs) setPlayhead(0)
            setPlaying((p) => !p)
            if (state.witness) dispatch({ type: 'witness', id: null })
          }}
          onSeek={(v) => {
            setPlaying(false)
            setPlayhead(v)
          }}
          onReset={() => {
            setPlaying(false)
            setPlayhead(null)
          }}
          reduced={reduced}
        />
      )}
    </div>
  )
}

function ViewLabel({ title, detail }: { title: string; detail: string }) {
  return (
    <p className="vp__label">
      <strong>{title}</strong>
      <span>{detail}</span>
    </p>
  )
}

function Scene({
  state,
  pose,
  relief,
  diff,
  controls,
  peer,
  fitOnMount = false,
  onSelect,
  onHover,
}: {
  state: WorkspaceState
  pose: Pose | null
  relief: Relief | null
  diff: GeometryDiff | null
  controls: MutableRefObject<CameraControls | null>
  peer: MutableRefObject<CameraControls | null> | null
  fitOnMount?: boolean
  onSelect: (id: PartId) => void
  onHover: (id: PartId | null) => void
}) {
  const view = useRef(createView('light'))
  const invalidate = useThree((s) => s.invalidate)

  useLayoutEffect(() => {
    composeView(view.current, { state, pose, relief })
    invalidate()
  })

  useEffect(() => {
    if (!fitOnMount) return
    const env = b02Manifest.envelope_mm
    const sphere = worldBox(env.min, env.max).getBoundingSphere(new THREE.Sphere())
    const raf = requestAnimationFrame(() => controls.current?.fitToSphere(sphere, false))
    return () => cancelAnimationFrame(raf)
  }, [fitOnMount, controls])

  // synchronised cameras: copy only while the user is driving this view, so the peer never echoes back
  useEffect(() => {
    const c = controls.current
    if (!c || !peer) return
    let driving = false
    const start = () => void (driving = true)
    const stop = () => void (driving = false)
    const copy = () => {
      const other = peer.current
      if (!driving || !other) return
      const p = c.getPosition(new THREE.Vector3())
      const t = c.getTarget(new THREE.Vector3())
      other.setLookAt(p.x, p.y, p.z, t.x, t.y, t.z, false)
    }
    c.addEventListener('controlstart', start)
    c.addEventListener('rest', stop)
    c.addEventListener('update', copy)
    return () => {
      c.removeEventListener('controlstart', start)
      c.removeEventListener('rest', stop)
      c.removeEventListener('update', copy)
    }
  }, [controls, peer])

  return (
    <>
      <color attach="background" args={['#ebeae5']} />
      <Studio theme="light" shadow={false} />
      <CameraControls ref={controls} makeDefault minDistance={0.9} maxDistance={14} smoothTime={0.22} draggingSmoothTime={0.08} />
      <Grid position={[0, -0.021, 0]} args={[12, 12]} cellSize={0.1} cellThickness={0.6} cellColor="#d3d1ca" sectionSize={0.5} sectionThickness={1} sectionColor="#b9b6ae" fadeDistance={9} fadeStrength={1.4} infiniteGrid />
      <ModuleAssembly view={view} interactive onSelect={onSelect} onHover={onHover} />
      {diff && <ChangedRegion diff={diff} />}
    </>
  )
}

/** Removed material from the geometry diff, drawn as a dashed cobalt volume. */
function ChangedRegion({ diff }: { diff: GeometryDiff }) {
  const { min, size, center, edges, mat } = useMemo(() => {
    const min = diff.region_min_mm
    const max = diff.region_max_mm
    const size: Vec3 = [max[0] - min[0], max[1] - min[1], max[2] - min[2]]
    const center: Vec3 = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2]
    const edges = new THREE.EdgesGeometry(new THREE.BoxGeometry(...size))
    const mat = new THREE.LineDashedMaterial({ color: '#2253d6', dashSize: 1.6, gapSize: 1.1 })
    return { min, size, center, edges, mat }
  }, [diff])
  const lines = useRef<THREE.LineSegments>(null)
  useLayoutEffect(() => {
    lines.current?.computeLineDistances()
  })
  void min
  return (
    <CadSpace>
      <group position={center}>
        <mesh raycast={() => null}>
          <boxGeometry args={size} />
          <meshBasicMaterial color="#3268f5" transparent opacity={0.16} depthWrite={false} />
        </mesh>
        <lineSegments ref={lines} geometry={edges} material={mat} raycast={() => null} />
      </group>
    </CadSpace>
  )
}

function PlaybackBar({
  segs,
  total,
  playhead,
  playing,
  current,
  compare,
  onPlay,
  onSeek,
  onReset,
  reduced,
}: {
  segs: Segment[]
  total: number
  playhead: number | null
  playing: boolean
  current?: Segment
  compare: boolean
  onPlay: () => void
  onSeek: (v: number) => void
  onReset: () => void
  reduced: boolean
}) {
  const step = playhead === null ? 0 : Math.min(total, Math.floor(playhead) + (playhead >= total ? 0 : 1))
  return (
    <div className="pb" role="group" aria-label="Path playback">
      <div className="pb__buttons">
        <button type="button" onClick={onReset} aria-label="Return to assembled pose" title="Assembled pose">
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d="M3 3v8M11 3L5 7l6 4z" fill="currentColor" stroke="currentColor" strokeWidth="1.2" />
          </svg>
        </button>
        <button type="button" onClick={() => onSeek(Math.max(0, Math.ceil((playhead ?? 0) - 1)))} aria-label="Previous step" title="Previous step ([)">
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d="M9.5 3L4.5 7l5 4z" fill="currentColor" />
          </svg>
        </button>
        <button type="button" className="pb__play" onClick={onPlay} aria-label={playing ? 'Pause' : 'Play'} title={reduced ? 'Play (motion reduced: use the step buttons)' : 'Play or pause (Space)'}>
          {playing ? (
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
              <path d="M4 3h2v8H4zM8 3h2v8H8z" fill="currentColor" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
              <path d="M4 2.5l7.5 4.5L4 11.5z" fill="currentColor" />
            </svg>
          )}
        </button>
        <button type="button" onClick={() => onSeek(Math.min(total, Math.floor((playhead ?? 0) + 1)))} aria-label="Next step" title="Next step (])">
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d="M4.5 3l5 4-5 4z" fill="currentColor" />
          </svg>
        </button>
      </div>
      <input
        className="pb__scrub"
        type="range"
        min={0}
        max={total}
        step={0.01}
        value={playhead ?? 0}
        onChange={(e) => onSeek(Number(e.target.value))}
        aria-label="Playback position"
        aria-valuetext={`Step ${step} of ${total}`}
        style={{ ['--pct' as string]: `${((playhead ?? 0) / total) * 100}%` }}
      />
      <p className="pb__label" aria-live="polite">
        <span className="mono">
          {step}/{total}
        </span>
        <span className={current?.kind === 'blocked' ? 'pb__blocked' : ''}>
          {current?.kind === 'blocked' && <Glyph kind="fail" />}
          {compare ? 'Synchronised by step index' : current?.label ?? `${segs.length} steps, assembled pose`}
        </span>
      </p>
      <span className="pb__prov" title="Fixture transforms replayed exactly between stored endpoints. Not a certified path.">
        Illustrative playback
      </span>
    </div>
  )
}
