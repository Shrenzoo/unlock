import { useEffect, useRef } from 'react'
import { createLightField, type FieldFrame, type LightField } from './lightField'
import { watchSectionLayout, type SectionLayout } from './sectionLayout'
import paperPlate from './field-hero.webp'
import nightPlate from './field-story.webp'
import './noise-field.css'

/** Ambient redraw rate; scrolling and pointer settling redraw every frame. */
const FRAME_MS = 1000 / 30
/** A pleasing still frame for reduced motion, and the starting point otherwise. */
const STILL_TIME = 8

const loadPlate = (src: string) => {
  const img = new Image()
  img.src = src
  return img.decode().then(() => img)
}

/** One continuous field across the landing page. Pointer and scroll motion never rerender React. */
export function NoiseField() {
  const field = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const el = field.current
    const cv = canvas.current
    if (!el || !cv) return
    const reduced = matchMedia('(prefers-reduced-motion: reduce)')
    const fine = matchMedia('(hover: hover) and (pointer: fine)')
    let layout: SectionLayout = { heroTop: 0, storyTop: 1e5, storyBottom: 1e5, footerTop: 1e5 }
    let gl: LightField | null = null
    let plates: { paper: HTMLImageElement; night: HTMLImageElement } | null = null
    let disposed = false

    const frame: FieldFrame = { time: STILL_TIME, shiftX: 0, shiftY: 0, heroTop: 0, storyTop: 1e5, storyBottom: 1e5, footerTop: 1e5 }
    let raf = 0, lastTick = 0, lastDraw = 0, sized = false
    let x = 0, y = 0, tx = 0, ty = 0, lastX = 0, lastY = 0
    const animating = () => !reduced.matches && !document.hidden

    const tick = (now: number) => {
      raf = 0
      const dt = Math.min((now - (lastTick || now)) / 1000, 0.1)
      lastTick = now
      const scroll = window.scrollY
      const ht = layout.heroTop - scroll
      const st = layout.storyTop - scroll, sb = layout.storyBottom - scroll, ft = layout.footerTop - scroll
      const scrolled = ht !== frame.heroTop || st !== frame.storyTop || sb !== frame.storyBottom || ft !== frame.footerTop
      frame.heroTop = ht; frame.storyTop = st; frame.storyBottom = sb; frame.footerTop = ft

      const k = 1 - Math.exp(-dt * 10)
      x += (tx - x) * k; y += (ty - y) * k
      const settling = Math.abs(tx - x) + Math.abs(ty - y) > 0.05
      const live = animating()
      if (live) frame.time += dt

      if (gl) {
        if (!sized) { gl.resize(innerWidth, innerHeight); sized = true }
        if (!lastDraw || scrolled || settling || (live && now - lastDraw >= FRAME_MS)) {
          frame.shiftX = x; frame.shiftY = y
          gl.render(frame)
          lastDraw = now
        }
      }
      if (scrolled) {
        // grain (and the CSS fallback) follow the same handover as the shader
        el.style.setProperty('--dusk', `${Math.min(st, ht + innerHeight)}px`)
        el.style.setProperty('--story-bottom', `${sb}px`)
        el.style.setProperty('--footer-top', `${ft}px`)
      }
      if ((live && gl) || settling) raf = requestAnimationFrame(tick)
      else lastTick = 0
    }
    const schedule = () => { if (!raf) raf = requestAnimationFrame(tick) }
    const resize = () => { sized = false; lastDraw = 0; schedule() }
    const start = () => {
      gl = plates && createLightField(cv, plates)
      el.dataset.field = gl ? 'ready' : 'fallback'
      frame.storyTop = NaN
      resize()
    }
    const move = (e: PointerEvent) => {
      if (reduced.matches || !fine.matches || e.pointerType === 'touch') return
      const dx = lastX ? Math.max(-30, Math.min(30, e.clientX - lastX)) : 0
      const dy = lastY ? Math.max(-30, Math.min(30, e.clientY - lastY)) : 0
      lastX = e.clientX; lastY = e.clientY
      tx = (e.clientX / innerWidth - 0.5) * 44 + dx * 0.5
      ty = (e.clientY / innerHeight - 0.5) * 32 + dy * 0.5
      schedule()
    }
    const reset = () => { tx = ty = lastX = lastY = 0; schedule() }
    const preferences = () => {
      if (reduced.matches) { x = y = tx = ty = 0; frame.time = STILL_TIME; lastDraw = 0 }
      schedule()
    }
    const lost = (e: Event) => { e.preventDefault(); gl = null; el.dataset.field = 'fallback'; frame.storyTop = NaN; schedule() }

    Promise.all([loadPlate(paperPlate), loadPlate(nightPlate)]).then(
      ([paper, night]) => { if (!disposed) { plates = { paper, night }; start() } },
      () => { if (!disposed) { el.dataset.field = 'fallback'; frame.storyTop = NaN; schedule() } },
    )
    schedule()
    const unwatch = watchSectionLayout((next) => { layout = next; schedule() })
    addEventListener('scroll', schedule, { passive: true })
    addEventListener('resize', resize, { passive: true })
    document.addEventListener('pointermove', move, { passive: true })
    document.documentElement.addEventListener('pointerleave', reset)
    document.addEventListener('visibilitychange', preferences)
    reduced.addEventListener('change', preferences)
    cv.addEventListener('webglcontextlost', lost)
    cv.addEventListener('webglcontextrestored', start)
    return () => {
      disposed = true
      unwatch()
      cancelAnimationFrame(raf)
      removeEventListener('scroll', schedule); removeEventListener('resize', resize)
      document.removeEventListener('pointermove', move)
      document.documentElement.removeEventListener('pointerleave', reset)
      document.removeEventListener('visibilitychange', preferences)
      reduced.removeEventListener('change', preferences)
      cv.removeEventListener('webglcontextlost', lost)
      cv.removeEventListener('webglcontextrestored', start)
      gl?.dispose()
    }
  }, [])
  return <div ref={field} className="noise-field" aria-hidden="true">
    <div className="noise-field__palette noise-field__palette--light" />
    <div className="noise-field__palette noise-field__palette--dark" />
    <canvas ref={canvas} className="noise-field__canvas" />
    <div className="noise-field__grain noise-field__grain--paper" />
    <div className="noise-field__grain noise-field__grain--night" />
  </div>
}
