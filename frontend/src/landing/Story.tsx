import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Line } from '@react-three/drei'
import { useEffect, useMemo, useRef, useState, type MutableRefObject } from 'react'
import * as THREE from 'three'
import { CadSpace, ModuleAssembly, createView } from '@/three/ModuleAssembly'
import { AnchorProjector, type Anchor } from '@/three/Anchors'
import { Studio } from '@/three/Studio'
import { FallbackDrawing } from '@/three/FallbackDrawing'
import { hasWebGL, prefersReducedMotion } from '@/three/units'
import { SCENES, applyStory, cameraAt, sceneAt } from './storyTimeline'
import { gsap, scrollToY } from './scroll'

const COPY = [
  {
    title: 'A small module with a part that will fail.',
    body: 'Chassis, top cover, a bridge bracket, a fan cartridge and the screws that hold them. Replacing a $5 part should not require destroying a $500 product.',
    note: 'Dollar figures are illustrative, not a measured case.',
  },
  {
    title: 'One failed part. An entire product in the way.',
    body: 'Lift the cover and the fan is right there, under the bracket web. So is the screw that holds it down.',
  },
  {
    title: 'The straight lift stops after 2.0 mm.',
    body: 'The fan’s swept volume meets the bracket web, and the driver cannot reach the fan screw either. The bracket is fixed in this product, so the search finds no supported route.',
    note: 'rej_sweep_fan, confirmed witness, travel 2.0 mm',
  },
  {
    title: 'Change the bracket, not the product.',
    body: 'One bounded edit from a supported family: a 52 × 16 mm relief through the web. Feet, posts and hole axes are protected and do not move.',
    note: 'Template T01, rectangular web relief',
  },
  {
    title: 'A way out.',
    body: 'The screw comes out, then the fan lifts straight through the relief. Seven operations, one tool, and only the cover removed along the way.',
    note: 'Illustrative sequence from fixture data, not a verification result.',
  },
]

const ANNOTS: Array<Anchor & { cls: string; mono: string; text?: string }> = [
  { id: 'witness', at: [-30, -34, 42], cls: 'annot annot--signal annot--left', mono: 'Fan / bracket contact', text: 'Witness after 2.0 mm of travel' },
  { id: 'tool', at: [24, -20, 48], cls: 'annot annot--signal', mono: 'Tool approach', text: 'Approach blocked at z 42.0 mm' },
  { id: 'dimW', at: [0, -40, 42], cls: 'annot annot--dim', mono: '52.0' },
  { id: 'dimD', at: [52, -20, 42], cls: 'annot annot--dim', mono: '16.0' },
  { id: 'protected', at: [56, 12, 8], cls: 'annot', mono: 'protected', text: 'Feet, posts and hole axes unchanged' },
  { id: 'path', at: [0, -20, 97], cls: 'annot annot--cobalt', mono: 'Removal direction', text: 'Z+ 64.0 mm, illustrative' },
]

export function Story() {
  const section = useRef<HTMLElement>(null)
  const progress = useRef(0)
  const invalidateRef = useRef<() => void>(() => {})
  const [scene, setScene] = useState(0)
  const webgl = useMemo(hasWebGL, [])
  const labels = useRef<Record<string, HTMLElement | null>>({})
  const annots = useRef<Record<string, HTMLElement | null>>({})

  useEffect(() => {
    const el = section.current
    if (!el) return
    const state = { p: 0 }
    const tween = gsap.to(state, {
      p: 1,
      ease: 'none',
      scrollTrigger: { trigger: el, start: 'top top', end: 'bottom bottom', scrub: prefersReducedMotion() ? true : 0.6 },
      onUpdate: () => {
        progress.current = state.p
        invalidateRef.current()
        const s = sceneAt(state.p)
        setScene((prev) => (prev === s ? prev : s))
      },
    })
    return () => {
      tween.scrollTrigger?.kill()
      tween.kill()
    }
  }, [])

  const jump = (i: number) => {
    const el = section.current
    if (!el) return
    const top = el.getBoundingClientRect().top + window.scrollY
    const span = el.offsetHeight - window.innerHeight
    scrollToY(top + span * (SCENES[i].start + (i === 0 ? 0 : 0.04)))
  }

  return (
    <section id="story" className="story" ref={section} aria-label="How UNLOCK works, in five steps">
      <div className="story__stage">
        <div className="story__canvas">
          {webgl ? (
            <Canvas frameloop="demand" dpr={[1, 2]} camera={{ fov: 30, position: [2.9, 1.65, 3.6], near: 0.05, far: 40 }} gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping }}>
              <StoryScene progress={progress} invalidateRef={invalidateRef} labels={labels} annots={annots} />
            </Canvas>
          ) : (
            <FallbackDrawing relief={scene >= 3} className="story__fallback" />
          )}
          {webgl && (
            <div className="anchors" aria-hidden="true">
              {ANNOTS.map((a) => (
                <div key={a.id} className="anchor" ref={(el) => void (labels.current[a.id] = el)}>
                  <div className={a.cls} style={{ opacity: 0 }} ref={(el) => void (annots.current[a.id] = el)}>
                    <span className="mono">{a.mono}</span>
                    {a.text && <span>{a.text}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="story__copy" aria-live="polite">
          {COPY.map((c, i) => (
            <article key={i} className={`story__panel ${i === scene ? 'is-active' : ''}`} aria-hidden={i !== scene}>
              <p className="story__index mono">
                {i + 1}
                <span>/5</span>
              </p>
              <h2>{c.title}</h2>
              <p className="story__body">{c.body}</p>
              {c.note && <p className="story__note mono">{c.note}</p>}
            </article>
          ))}
        </div>

        <nav className="story__rail" aria-label="Story steps">
          <ol>
            {SCENES.map((s, i) => (
              <li key={s.id}>
                <button type="button" className={i === scene ? 'is-active' : ''} aria-current={i === scene ? 'step' : undefined} onClick={() => jump(i)}>
                  <span className="mono">{i + 1}</span>
                  <span className="story__step-name">{s.label}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>
      </div>
    </section>
  )
}

function StoryScene({
  progress,
  invalidateRef,
  labels,
  annots,
}: {
  progress: MutableRefObject<number>
  invalidateRef: MutableRefObject<() => void>
  labels: MutableRefObject<Record<string, HTMLElement | null>>
  annots: MutableRefObject<Record<string, HTMLElement | null>>
}) {
  const view = useRef(createView('dark'))
  const { camera, invalidate, size } = useThree()
  const target = useMemo(() => new THREE.Vector3(), [])
  const lines = useRef<Record<string, THREE.Material | null>>({})

  useEffect(() => {
    invalidateRef.current = invalidate
  }, [invalidate, invalidateRef])

  useEffect(() => {
    const cam = camera as THREE.PerspectiveCamera
    cam.filmOffset = 0
    cam.updateProjectionMatrix()
    invalidate()
  }, [camera, invalidate])

  useFrame(() => {
    const p = progress.current
    applyStory(p, view.current)
    const c = cameraAt(p)
    // Fit a conservative sphere around every story pose, including lifted parts.
    // The camera keeps the authored direction without cropping a narrow viewport.
    const aspect = size.width / Math.max(1, size.height)
    const cam = camera as THREE.PerspectiveCamera
    const vertical = THREE.MathUtils.degToRad(cam.fov)
    const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * aspect)
    const opening = Math.min(1, Math.max(0, (p - 0.1) / 0.14))
    const radius = THREE.MathUtils.lerp(1.3, 1.6, opening)
    const needed = radius / Math.sin(Math.min(vertical, horizontal) / 2)
    target.set(c.target[0], THREE.MathUtils.lerp(0.32, 0.65, opening) + (c.target[1] - 0.3) * 0.25, c.target[2])
    const dx = c.pos[0] - c.target[0], dy = c.pos[1] - c.target[1], dz = c.pos[2] - c.target[2]
    const k = Math.max(0.52, needed / Math.hypot(dx, dy, dz))
    camera.position.set(target.x + dx * k, target.y + dy * k * 1.12, target.z + dz * k)
    cam.clearViewOffset()
    camera.lookAt(target)

    const show = (key: string, a: number, b: number, fade = 0.015) => {
      const t = Math.min(1, Math.max(0, Math.min((p - a) / fade, (b - p) / fade)))
      const el = annots.current[key]
      if (el) el.style.opacity = String(t)
      const mat = lines.current[key]
      if (mat) {
        mat.opacity = t
        mat.visible = t > 0.01
      }
    }
    show('witness', 0.41, 0.56)
    show('tool', 0.51, 0.56)
    show('dimW', 0.69, 0.79)
    show('dimD', 0.69, 0.79)
    show('dimLineW', 0.69, 0.79)
    show('dimLineD', 0.69, 0.79)
    show('protected', 0.62, 0.79)
    show('path', 0.8, 1.01)
    show('pathLine', 0.8, 1.01)
  })

  const line = (key: string) => (l: THREE.Object3D | null) => {
    const mat = (l as THREE.Mesh | null)?.material as THREE.Material | undefined
    lines.current[key] = mat ?? null
    if (mat) {
      mat.transparent = true
      mat.opacity = 0
    }
  }

  const tick = (x: number, y: number, z: number, axis: 'x' | 'y'): [number, number, number][] =>
    axis === 'x'
      ? [
          [x, y - 2, z],
          [x, y + 2, z],
        ]
      : [
          [x - 2, y, z],
          [x + 2, y, z],
        ]

  return (
    <>
      <Studio theme="dark" polished />
      <ModuleAssembly view={view} polished />
      <AnchorProjector anchors={ANNOTS} targets={labels} />
      <CadSpace>
        {/* scene 4 dimensions of the relief, constructor parameters */}
        <Line ref={line('dimLineW')} points={[[-26, -40, 42], [26, -40, 42], ...tick(-26, -40, 42, 'x'), ...tick(26, -40, 42, 'x')]} segments color="#7fa2ff" lineWidth={1} />
        <Line ref={line('dimLineD')} points={[[52, -28, 42], [52, -12, 42], ...tick(52, -28, 42, 'y'), ...tick(52, -12, 42, 'y')]} segments color="#7fa2ff" lineWidth={1} />

        {/* scene 5 extraction path, straight Z+ segment to staging */}
        <Line ref={line('pathLine')} points={[[0, -20, 21], [0, -20, 21 + 74]]} color="#7fa2ff" lineWidth={1.2} dashed dashSize={3} gapSize={2.2} />
      </CadSpace>
    </>
  )
}
