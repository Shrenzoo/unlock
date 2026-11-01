import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef, type MutableRefObject } from 'react'
import * as THREE from 'three'
import type { Vec3 } from '@/domain/types'
import { CadSpace } from './ModuleAssembly'

export interface Anchor {
  id: string
  /** CAD millimetres, in the same space as the assembly */
  at: Vec3
}

/**
 * Projects CAD-space anchor points to screen pixels on every rendered frame and
 * writes them straight to DOM labels — annotations stay crisp HTML without
 * mounting extra React roots inside the canvas.
 */
export function AnchorProjector({ anchors, targets }: { anchors: Anchor[]; targets: MutableRefObject<Record<string, HTMLElement | null>> }) {
  const space = useRef<THREE.Group>(null)
  const { camera, size } = useThree()
  const v = useMemo(() => new THREE.Vector3(), [])
  useEffect(() => {
    for (const a of anchors) targets.current[a.id]?.style.setProperty('--stage-width', `${size.width}px`)
  }, [anchors, targets, size.width])

  useFrame(() => {
    const g = space.current
    if (!g) return
    g.updateWorldMatrix(true, false)
    for (const a of anchors) {
      const el = targets.current[a.id]
      if (!el) continue
      v.set(a.at[0], a.at[1], a.at[2]).applyMatrix4(g.matrixWorld).project(camera)
      const behind = v.z > 1
      const x = ((v.x + 1) / 2) * size.width
      const y = ((1 - v.y) / 2) * size.height
      el.style.setProperty('--anchor-x', `${x.toFixed(1)}px`)
      el.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`
      el.style.visibility = behind ? 'hidden' : ''
    }
  })

  return (
    <CadSpace>
      <group ref={space} />
    </CadSpace>
  )
}
