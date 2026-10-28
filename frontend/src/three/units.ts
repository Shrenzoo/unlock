/**
 * The single millimetre → render-unit conversion (PRD §18: apply scale once).
 * Analysis geometry stays in mm; only the CAD-space group is scaled.
 * 1 render unit = 100 mm keeps camera and light values readable.
 */
export const MM = 0.01

/** CAD frame is Z up; three.js is Y up. Children of <CadSpace> are authored in CAD mm. */
export const CAD_ROTATION: [number, number, number] = [-Math.PI / 2, 0, 0]

export function hasWebGL(): boolean {
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch {
    return false
  }
}

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
