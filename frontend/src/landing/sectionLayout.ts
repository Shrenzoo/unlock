export type SectionLayout = { heroTop: number; storyTop: number; storyBottom: number; footerTop: number }

const listeners = new Set<(layout: SectionLayout) => void>()
let layout: SectionLayout = { heroTop: 0, storyTop: Infinity, storyBottom: Infinity, footerTop: Infinity }
let stop: (() => void) | null = null

/** Document coordinates change with layout, not with every animation frame. */
export function watchSectionLayout(listener: (layout: SectionLayout) => void) {
  listeners.add(listener)
  if (!stop) {
    const hero = document.querySelector('.hero')
    const story = document.getElementById('story')
    const footer = document.querySelector('.footer')
    let raf = 0
    const measure = () => {
      raf = 0
      const y = window.scrollY
      const h = hero?.getBoundingClientRect()
      const s = story?.getBoundingClientRect()
      const f = footer?.getBoundingClientRect()
      layout = { heroTop: (h?.top ?? -y) + y, storyTop: (s?.top ?? Infinity) + y, storyBottom: (s?.bottom ?? Infinity) + y, footerTop: (f?.top ?? Infinity) + y }
      for (const notify of listeners) notify(layout)
    }
    const schedule = () => { if (!raf) raf = requestAnimationFrame(measure) }
    const observer = new ResizeObserver(schedule)
    for (const el of [hero, story, footer, document.querySelector('.landing main')]) if (el) observer.observe(el)
    window.addEventListener('resize', schedule, { passive: true })
    stop = () => { cancelAnimationFrame(raf); observer.disconnect(); window.removeEventListener('resize', schedule) }
    measure()
  } else listener(layout)
  return () => {
    listeners.delete(listener)
    if (!listeners.size) { stop?.(); stop = null }
  }
}
