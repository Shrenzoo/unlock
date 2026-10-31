import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { b02Manifest } from '@/fixtures/b02'
import { SAMPLE_PROJECT_PATH } from '@/api'
import { Link } from '@/router'
import { ModuleAssembly, PART_IDS, createView, type PartId } from '@/three/ModuleAssembly'
import { Studio } from '@/three/Studio'
import { FallbackDrawing } from '@/three/FallbackDrawing'
import { hasWebGL, prefersReducedMotion } from '@/three/units'
import { gsap, scrollToId } from './scroll'

const COVER_SCREWS = ['screw_c1', 'screw_c2', 'screw_c3', 'screw_c4'] as const
const EXPLODE = { cover: 50, screws: 74 }

const ISOLATABLE: PartId[] = ['fan_module', 'bridge_bracket', 'cover']
const PART_LABELS: Record<string, string> = { fan_module: 'Fan module', bridge_bracket: 'Bridge bracket', cover: 'Top cover' }

export function Hero() {
  const webgl = useMemo(hasWebGL, [])
  const [hovered, setHovered] = useState<PartId | null>(null)
  const [isolated, setIsolated] = useState<PartId | null>(null)
  const focus = isolated ?? hovered
  const comp = focus ? b02Manifest.components.find((c) => c.id === focus) : null

  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero__stage">
        {webgl ? (
          <Canvas
            frameloop="demand"
            dpr={[1, 2]}
            camera={{ fov: 24, position: [2.7, 1.55, 3.4], near: 0.1, far: 40 }}
            gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.05 }}
            onPointerMissed={() => setIsolated(null)}
            aria-label="Interactive model of the B02 service module. Drag to turn it; select a part to isolate it."
          >
            <HeroScene hovered={hovered} isolated={isolated} onHover={setHovered} onIsolate={setIsolated} />
          </Canvas>
        ) : null}
        {!webgl && (
          <div className="hero__fallback">
            <FallbackDrawing />
            <p>3D preview unavailable in this browser. The drawing shows the same module.</p>
          </div>
        )}
      </div>

      <div className="hero__copy">
        <h1 id="hero-title" className="hero__title">
          Design for
          <br /> the day it
          <br /> breaks.
        </h1>
        <p className="hero__lede">Find what blocks repair. Change the design. Verify the way out.</p>
        <div className="hero__ctas">
          <Link to={SAMPLE_PROJECT_PATH} className="btn btn--primary">
            <span className="btn__key" aria-hidden="true" />
            Explore UNLOCK
          </Link>
          <a
            href="#story"
            className="btn btn--quiet"
            onClick={(e) => {
              e.preventDefault()
              scrollToId('story')
            }}
          >
            See how it works
          </a>
        </div>
      </div>

      <aside className="titleblock" aria-label="Drawing title block">
        <div className="titleblock__row titleblock__row--head">
          <span className="mono">B02</span>
          <span>Trapped fan bridge</span>
        </div>
        <div className="titleblock__row titleblock__grid">
          <span>
            <i>Rev</i> A
          </span>
          <span>
            <i>Units</i> mm
          </span>
          <span>
            <i>Frame</i> Z up
          </span>
        </div>
        <div className="titleblock__row titleblock__part" aria-live="polite">
          {comp ? (
            <>
              <span>{PART_LABELS[comp.id] ?? comp.id}</span>
              <span>{comp.fixed ? 'Fixed' : comp.replaceable ? 'Replaceable' : 'Removable'}{comp.removal_axes.length ? `, ${comp.removal_axes.join(' ')}` : ''}</span>
            </>
          ) : (
            <span className="titleblock__hint">Drag to turn. Select a part to isolate it.</span>
          )}
        </div>
        <div className="titleblock__row titleblock__parts" role="group" aria-label="Isolate a part">
          {ISOLATABLE.map((id) => (
            <button key={id} type="button" aria-pressed={isolated === id} onClick={() => setIsolated(isolated === id ? null : id)}>
              {PART_LABELS[id]}
            </button>
          ))}
        </div>
        <p className="titleblock__note">Synthetic fixture. Presentation geometry, not analysis output.</p>
      </aside>
    </section>
  )
}

function HeroScene({
  hovered,
  isolated,
  onHover,
  onIsolate,
}: {
  hovered: PartId | null
  isolated: PartId | null
  onHover: (id: PartId | null) => void
  onIsolate: (id: PartId | null) => void
}) {
  const view = useRef(createView('light'))
  const rig = useRef<THREE.Group>(null)
  const { camera, invalidate, size, gl } = useThree()
  const target = useMemo(() => new THREE.Vector3(0, 0.65, 0), [])
  const motion = useRef({ yaw: 0, pitch: 0, baseYaw: 0, basePitch: 0, px: 0, py: 0, dragging: false })
  const reduced = useMemo(prefersReducedMotion, [])

  // The scene has its own column: frame the entire exploded assembly in it.
  useEffect(() => {
    const cam = camera as THREE.PerspectiveCamera
    const aspect = size.width / Math.max(1, size.height)
    const k = Math.max(1, 1.05 / aspect)
    cam.filmOffset = 0
    cam.fov = 32
    cam.position.set(3 * k, 2.7 * k, 4.3 * k)
    cam.lookAt(target)
    cam.updateProjectionMatrix()
    invalidate()
  }, [camera, size.width, size.height, target, invalidate])

  // one orchestrated reveal: screws lift, then the cover, exposing the bracket and fan
  useEffect(() => {
    const v = view.current
    v.parts.fan_module.tone = 'target'
    // see-through aluminium walls; base plate and feet stay solid
    v.parts.chassis.fade = { aluminum: 0.2 }
    const apply = (t: { s: number; c: number }) => {
      for (const id of COVER_SCREWS) v.parts[id].offset[2] = EXPLODE.screws * t.s
      v.parts.cover.offset[2] = EXPLODE.cover * t.c
      invalidate()
    }
    const state = { s: 0, c: 0 }
    if (reduced) {
      apply({ s: 1, c: 1 })
      return
    }
    const tl = gsap.timeline({ delay: 0.35 })
    tl.to(state, { s: 1, duration: 1.0, ease: 'power3.inOut', onUpdate: () => apply(state) })
    tl.to(state, { c: 1, duration: 1.15, ease: 'power3.inOut', onUpdate: () => apply(state) }, 0.3)
    return () => {
      tl.kill()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // isolation: fade everything except the chosen part
  useEffect(() => {
    const v = view.current
    const from = Object.fromEntries(PART_IDS.map((id) => [id, v.parts[id].opacity]))
    const to = Object.fromEntries(PART_IDS.map((id) => [id, !isolated || id === isolated ? 1 : 0.1]))
    const o = { t: 0 }
    const tw = gsap.to(o, {
      t: 1,
      duration: reduced ? 0 : 0.32,
      ease: 'power2.out',
      onUpdate: () => {
        for (const id of PART_IDS) v.parts[id].opacity = from[id] + (to[id] - from[id]) * o.t
        invalidate()
      },
    })
    return () => {
      tw.kill()
    }
  }, [isolated, invalidate, reduced])

  useEffect(() => {
    for (const id of PART_IDS) view.current.parts[id].hover = id === hovered
    invalidate()
  }, [hovered, invalidate])

  // drag to turn (bounded), plus a slight pointer parallax
  useEffect(() => {
    const el = gl.domElement
    const m = motion.current
    let lastX = 0
    let lastY = 0
    const down = (e: PointerEvent) => {
      m.dragging = true
      lastX = e.clientX
      lastY = e.clientY
      el.setPointerCapture(e.pointerId)
    }
    const move = (e: PointerEvent) => {
      if (m.dragging) {
        m.baseYaw = Math.max(-1.1, Math.min(1.1, m.baseYaw + (e.clientX - lastX) * 0.006))
        m.basePitch = Math.max(-0.25, Math.min(0.32, m.basePitch + (e.clientY - lastY) * 0.003))
        lastX = e.clientX
        lastY = e.clientY
      } else if (!reduced) {
        m.px = (e.clientX / window.innerWidth - 0.5) * 0.08
        m.py = (e.clientY / window.innerHeight - 0.5) * 0.04
      }
      invalidate()
    }
    const up = (e: PointerEvent) => {
      m.dragging = false
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId)
    }
    const dbl = () => {
      m.baseYaw = 0
      m.basePitch = 0
      invalidate()
    }
    el.addEventListener('pointerdown', down)
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    el.addEventListener('dblclick', dbl)
    el.style.touchAction = 'pan-y'
    return () => {
      el.removeEventListener('pointerdown', down)
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      el.removeEventListener('dblclick', dbl)
    }
  }, [gl, invalidate, reduced])

  useFrame((_, dt) => {
    const m = motion.current
    const k = 1 - Math.exp(-dt * 9)
    const ty = m.baseYaw + m.px
    const tp = m.basePitch + m.py
    m.yaw += (ty - m.yaw) * k
    m.pitch += (tp - m.pitch) * k
    if (rig.current) {
      rig.current.rotation.y = m.yaw
      rig.current.rotation.x = m.pitch
    }
    if (Math.abs(ty - m.yaw) > 1e-4 || Math.abs(tp - m.pitch) > 1e-4) invalidate()
  })

  return (
    <>
      <Studio theme="light" />
      <group ref={rig}>
        <ModuleAssembly view={view} interactive onHover={onHover} onSelect={(id) => onIsolate(isolated === id ? null : id)} />
      </group>
    </>
  )
}
