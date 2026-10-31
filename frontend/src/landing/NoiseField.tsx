import { useEffect, useRef } from 'react'
import './noise-field.css'

const clamp = (n: number) => Math.max(0, Math.min(1, n))
const smooth = (n: number) => { const t = clamp(n); return t * t * (3 - 2 * t) }

/** One continuous field across the landing page. Pointer motion never rerenders React. */
export function NoiseField() {
  const field = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = field.current
    if (!el) return
    const reduced = matchMedia('(prefers-reduced-motion: reduce)')
    const fine = matchMedia('(hover: hover) and (pointer: fine)')
    const story = document.getElementById('story')
    const footer = document.querySelector('.footer')
    let scrollFrame = 0, pointerFrame = 0, lastTime = 0
    let x = 0, y = 0, tx = 0, ty = 0, lastX = 0, lastY = 0
    const palette = () => {
      scrollFrame = 0
      const vh = innerHeight
      const r = story?.getBoundingClientRect()
      const f = footer?.getBoundingClientRect()
      el.style.setProperty('--story-top', `${r?.top ?? 100000}px`)
      el.style.setProperty('--story-bottom', `${r?.bottom ?? 100000}px`)
      el.style.setProperty('--footer-top', `${f?.top ?? 100000}px`)
      const enter = r ? smooth((vh * 0.85 - r.top) / (vh * 0.75)) : 0
      const leave = r ? smooth((r.bottom - vh * 0.15) / (vh * 0.75)) : 0
      const end = f ? smooth((vh * 0.85 - f.top) / (vh * 0.75)) : 0
      el.style.setProperty('--field-dark', String(Math.max(enter * leave, end)))
    }
    const scroll = () => { if (!scrollFrame) scrollFrame = requestAnimationFrame(palette) }
    const settle = (now: number) => {
      const dt = Math.min((now - (lastTime || now)) / 1000, 0.05)
      lastTime = now
      const k = 1 - Math.exp(-dt * 10)
      x += (tx - x) * k; y += (ty - y) * k
      el.style.setProperty('--field-x', `${x.toFixed(2)}px`)
      el.style.setProperty('--field-y', `${y.toFixed(2)}px`)
      if (Math.abs(tx - x) + Math.abs(ty - y) > 0.05) pointerFrame = requestAnimationFrame(settle)
      else { pointerFrame = 0; lastTime = 0 }
    }
    const move = (e: PointerEvent) => {
      if (reduced.matches || !fine.matches || e.pointerType === 'touch') return
      const dx = lastX ? Math.max(-30, Math.min(30, e.clientX - lastX)) : 0
      const dy = lastY ? Math.max(-30, Math.min(30, e.clientY - lastY)) : 0
      lastX = e.clientX; lastY = e.clientY
      tx = (e.clientX / innerWidth - 0.5) * 44 + dx * 0.5
      ty = (e.clientY / innerHeight - 0.5) * 32 + dy * 0.5
      if (!pointerFrame) pointerFrame = requestAnimationFrame(settle)
    }
    const reset = () => {
      tx = ty = lastX = lastY = 0
      if (!reduced.matches && !pointerFrame) pointerFrame = requestAnimationFrame(settle)
    }
    const preferences = () => {
      el.dataset.paused = String(document.hidden || reduced.matches)
      if (reduced.matches) {
        cancelAnimationFrame(pointerFrame); pointerFrame = 0
        x = y = tx = ty = 0
        el.style.setProperty('--field-x', '0px'); el.style.setProperty('--field-y', '0px')
      }
    }
    palette(); preferences()
    addEventListener('scroll', scroll, { passive: true })
    addEventListener('resize', scroll, { passive: true })
    document.addEventListener('pointermove', move, { passive: true })
    document.documentElement.addEventListener('pointerleave', reset)
    document.addEventListener('visibilitychange', preferences)
    reduced.addEventListener('change', preferences)
    return () => {
      cancelAnimationFrame(scrollFrame); cancelAnimationFrame(pointerFrame)
      removeEventListener('scroll', scroll); removeEventListener('resize', scroll)
      document.removeEventListener('pointermove', move)
      document.documentElement.removeEventListener('pointerleave', reset)
      document.removeEventListener('visibilitychange', preferences)
      reduced.removeEventListener('change', preferences)
    }
  }, [])
  return <div ref={field} className="noise-field" aria-hidden="true">
    <div className="noise-field__palette noise-field__palette--light"><div className="noise-field__pointer"><div className="noise-field__cloud noise-field__cloud--blue" /><div className="noise-field__cloud noise-field__cloud--ink" /></div></div>
    <div className="noise-field__palette noise-field__palette--dark"><div className="noise-field__pointer"><div className="noise-field__cloud noise-field__cloud--blue" /><div className="noise-field__cloud noise-field__cloud--white" /></div></div>
    <div className="noise-field__grain" />
  </div>
}
