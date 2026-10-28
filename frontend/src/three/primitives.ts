import * as THREE from 'three'
import type { Vec3 } from '@/domain/types'

/**
 * Presentation-geometry builders, authored in CAD millimetres (Z up).
 * These meshes are for display and selection only; they never certify clearance.
 */

export type Mat = 'aluminum' | 'anodized' | 'steel' | 'oxide' | 'plastic' | 'rubber' | 'board' | 'chip' | 'connector' | 'cap'

export interface Solid {
  geometry: THREE.BufferGeometry
  edges: THREE.BufferGeometry
  mat: Mat
  /** stable key for animated pieces (bracket web segments) */
  key?: string
}

const EDGE_ANGLE = 28
const unitBox = new THREE.BoxGeometry(1, 1, 1)
const unitBoxEdges = new THREE.EdgesGeometry(unitBox, EDGE_ANGLE)

function solid(geometry: THREE.BufferGeometry, mat: Mat, key?: string): Solid {
  return { geometry, edges: new THREE.EdgesGeometry(geometry, EDGE_ANGLE), mat, key }
}

/** Axis-aligned box from world-mm corners. Baked so edges stay crisp. */
export function box(min: Vec3, max: Vec3, mat: Mat, key?: string): Solid {
  const g = new THREE.BoxGeometry(max[0] - min[0], max[1] - min[1], max[2] - min[2])
  g.translate((min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2)
  return solid(g, mat, key)
}

/** Unit box for pieces whose size animates (scale/position set per frame). */
export function unitSolid(mat: Mat, key: string): Solid {
  return { geometry: unitBox, edges: unitBoxEdges, mat, key }
}

/** Cylinder with its axis along world Z. */
export function cylZ(x: number, y: number, z0: number, z1: number, r: number, mat: Mat, seg = 28): Solid {
  const g = new THREE.CylinderGeometry(r, r, z1 - z0, seg)
  g.rotateX(Math.PI / 2)
  g.translate(x, y, (z0 + z1) / 2)
  return solid(g, mat)
}

/** Cylinder with its axis along world Y. */
export function cylY(x: number, z: number, y0: number, y1: number, r: number, mat: Mat, seg = 28): Solid {
  const g = new THREE.CylinderGeometry(r, r, Math.abs(y1 - y0), seg)
  g.translate(x, (y0 + y1) / 2, z)
  return solid(g, mat)
}

type Hole = { rect: [number, number, number, number] } | { circle: [number, number, number] }

function rectPath(u0: number, v0: number, u1: number, v1: number, path: THREE.Path = new THREE.Path()) {
  path.moveTo(u0, v0)
  path.lineTo(u1, v0)
  path.lineTo(u1, v1)
  path.lineTo(u0, v1)
  path.closePath()
  return path
}

/**
 * Flat plate in a UV plane extruded by `thickness` along W, with holes.
 * basis maps local (U, V, W) to world axes; origin is the world position of U=0,V=0,W=0.
 */
export function plate(
  outline: [number, number, number, number],
  holes: Hole[],
  thickness: number,
  basis: [Vec3, Vec3, Vec3],
  origin: Vec3,
  mat: Mat,
  bevel = 0,
): Solid {
  const [u0, v0, u1, v1] = outline
  const shape = new THREE.Shape()
  rectPath(u0 + bevel, v0 + bevel, u1 - bevel, v1 - bevel, shape)
  for (const h of holes) {
    if ('rect' in h) shape.holes.push(rectPath(h.rect[0], h.rect[1], h.rect[2], h.rect[3]))
    else {
      const p = new THREE.Path()
      p.absarc(h.circle[0], h.circle[1], h.circle[2], 0, Math.PI * 2, true)
      shape.holes.push(p)
    }
  }
  const g = new THREE.ExtrudeGeometry(shape, {
    depth: thickness - bevel * 2,
    bevelEnabled: bevel > 0,
    bevelThickness: bevel,
    bevelSize: bevel,
    bevelSegments: 1,
    curveSegments: 24,
  })
  if (bevel > 0) g.translate(0, 0, bevel)
  const m = new THREE.Matrix4().makeBasis(new THREE.Vector3(...basis[0]), new THREE.Vector3(...basis[1]), new THREE.Vector3(...basis[2]))
  m.setPosition(...origin)
  g.applyMatrix4(m)
  return solid(g, mat)
}

export const BASIS = {
  /** plate in XY, extruded up Z */
  xyUp: [
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
  ] as [Vec3, Vec3, Vec3],
  /** plate in XZ (U=x, V=z), extruded toward -Y */
  xzFront: [
    [1, 0, 0],
    [0, 0, 1],
    [0, -1, 0],
  ] as [Vec3, Vec3, Vec3],
  /** plate in YZ (U=y, V=z), extruded toward +X */
  yzSide: [
    [0, 1, 0],
    [0, 0, 1],
    [1, 0, 0],
  ] as [Vec3, Vec3, Vec3],
}

export interface MatSpec {
  color: string
  metalness: number
  roughness: number
}

export const MATERIALS: Record<Mat, MatSpec> = {
  aluminum: { color: '#c7c9ca', metalness: 0.82, roughness: 0.36 },
  anodized: { color: '#3b3f43', metalness: 0.55, roughness: 0.48 },
  steel: { color: '#a3a8ab', metalness: 0.9, roughness: 0.28 },
  oxide: { color: '#2a2c2e', metalness: 0.7, roughness: 0.34 },
  plastic: { color: '#2c2f32', metalness: 0.0, roughness: 0.58 },
  rubber: { color: '#1b1c1d', metalness: 0.0, roughness: 0.92 },
  board: { color: '#202326', metalness: 0.1, roughness: 0.62 },
  chip: { color: '#121314', metalness: 0.2, roughness: 0.45 },
  connector: { color: '#e4e0d6', metalness: 0.0, roughness: 0.6 },
  cap: { color: '#b9bcbe', metalness: 0.85, roughness: 0.32 },
}
