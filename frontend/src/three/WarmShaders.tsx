import { useThree } from '@react-three/fiber'
import { useEffect } from 'react'
import * as THREE from 'three'

/** Compile both fade paths before scrolling, without drawing or changing a frame. */
export function WarmShaders() {
  const { gl, scene, camera } = useThree()
  useEffect(() => {
    let active = true, raf = 0, idle = 0, timer = 0
    const prepare = () => {
      const materials = new Map<THREE.MeshStandardMaterial, boolean>()
      scene.traverse((object) => {
        const material = (object as THREE.Mesh).material
        for (const m of Array.isArray(material) ? material : [material]) {
          if (m instanceof THREE.MeshStandardMaterial) materials.set(m, m.transparent)
        }
      })
      const jobs: Promise<unknown>[] = []
      try {
        for (const transparent of [false, true]) {
          for (const m of materials.keys()) { m.transparent = transparent; m.needsUpdate = true }
          jobs.push(gl.compileAsync(scene, camera))
        }
      } catch (error) {
        jobs.push(Promise.reject(error))
      } finally {
        // Restore synchronously before the browser can draw the next frame.
        for (const [m, transparent] of materials) { m.transparent = transparent; m.needsUpdate = true }
      }
      void Promise.all(jobs).then(() => {
        if (active) gl.domElement.dataset.shaders = 'ready'
      }, () => { if (active) gl.domElement.dataset.shaders = 'unavailable' })
    }
    const waitForStudio = () => {
      if (!scene.environment) { raf = requestAnimationFrame(waitForStudio); return }
      if ('requestIdleCallback' in window) idle = window.requestIdleCallback(prepare, { timeout: 500 })
      else timer = setTimeout(prepare, 0)
    }
    raf = requestAnimationFrame(waitForStudio)
    return () => { active = false; cancelAnimationFrame(raf); if (idle) window.cancelIdleCallback(idle); clearTimeout(timer) }
  }, [gl, scene, camera])
  return null
}
