import { ThreeCanvas } from '@remotion/three'
import { useMemo } from 'react'
import * as THREE from 'three'
import { b05, type Mesh } from '../data'
import { C, PART } from '../theme'

/**
 * The B05 battery bay drawn from the engine's own tessellation (mm, Z up).
 * Every visual state is a plain prop computed from the current frame, so a
 * rendered frame never depends on wall-clock time.
 */
export type ModelState = {
  azimuth: number // orbit about the vertical axis, radians
  scale: number // overall zoom
  y: number // world-units shift, to leave headroom for the lift
  parts: number // 0..1 fade of the whole assembly
  probeZ: number // mm lift of the translucent probe of the pack
  probe: number // 0..1 probe opacity
  probeColor: string
  strapTint: number // 0 neutral -> 1 obstacle amber
  revised: number // 0 original strap -> 1 the verified design
  checked: number // 0 candidate tone -> 1 checked green
  sweep: number // construction sweep 0..1, or -1 for none
  witness: number // 0..1 visibility of the BRep contact marker
  pulse: number // 0..1 ring phase
  packZ: number // mm lift of the real pack
  path: number // 0..1 drawn length of the removal path
}

const MM = 0.01 // world units per mm
const CENTER: [number, number, number] = [0, 0, -12] // mm, recentres the bay

function geometry(m: Mesh) {
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.Float32BufferAttribute(m.vertices, 3))
  g.setIndex(m.indices)
  g.computeVertexNormals()
  return g
}

function tone(role: string) {
  if (role === 'electronics') return PART.electronics
  if (role === 'fastener') return PART.fastener
  if (role === 'service_module') return PART.target
  return PART.neutral
}

const mix = (a: string, b: string, t: number) =>
  '#' + new THREE.Color(a).lerp(new THREE.Color(b), Math.min(1, Math.max(0, t))).getHexString()

const Part: React.FC<{
  geo: THREE.BufferGeometry
  edges: THREE.EdgesGeometry
  color: string
  opacity: number
  z?: number
}> = ({ geo, edges, color, opacity, z = 0 }) => {
  if (opacity <= 0.001) return null
  const solid = opacity >= 0.999
  return (
    <group position={[0, 0, z]}>
      <mesh geometry={geo}>
        <meshStandardMaterial
          color={color}
          metalness={0.35}
          roughness={0.45}
          transparent={!solid}
          opacity={opacity}
          depthWrite={solid}
        />
      </mesh>
      <lineSegments geometry={edges}>
        <lineBasicMaterial color={C.ink} transparent opacity={0.3 * opacity} />
      </lineSegments>
    </group>
  )
}

export const B05Model: React.FC<{ width: number; height: number; s: ModelState }> = ({
  width,
  height,
  s,
}) => {
  const parts = useMemo(
    () =>
      b05.components.map((c) => {
        const geo = geometry(c)
        return { id: c.id, role: c.role, geo, edges: new THREE.EdgesGeometry(geo, 28) }
      }),
    [],
  )
  const revised = useMemo(() => {
    const geo = geometry(b05.revised_bridge)
    return { geo, edges: new THREE.EdgesGeometry(geo, 28) }
  }, [])
  const target = parts.find((p) => p.id === 'target')!
  const bridge = parts.find((p) => p.id === 'bridge')!
  const [wx, wy, wz] = b05.witness.point_mm
  // Pack box: x -22..22, y 4..26, z 10..26; the path starts at its top centre.
  const pathStart: [number, number, number] = [0, 15, 26]
  const pathLength = b05.removal.distance_mm * s.path
  const strapColor = mix(PART.neutral, PART.obstacle, s.strapTint)
  const revisedColor = mix(PART.candidate, PART.checked, s.checked)

  return (
    <ThreeCanvas
      width={width}
      height={height}
      camera={{ fov: 28, position: [0, 2.15, 4.3], rotation: [-Math.atan2(2.15, 4.3), 0, 0] }}
      gl={{ antialias: true, alpha: true }}
    >
      <ambientLight intensity={0.55} />
      <hemisphereLight args={['#ffffff', '#b9b4a7', 0.55]} />
      <directionalLight position={[3, 5, 4]} intensity={1.5} />
      <directionalLight position={[-4, 2, -3]} intensity={0.35} />
      <group position={[0, s.y, 0]} rotation={[0, s.azimuth, 0]} scale={s.scale}>
        <group rotation={[-Math.PI / 2, 0, 0]} scale={MM}>
          <group position={CENTER}>
            {parts
              .filter((p) => p.id !== 'bridge' && p.id !== 'target')
              .map((p) => (
                <Part key={p.id} geo={p.geo} edges={p.edges} color={tone(p.role)} opacity={s.parts} />
              ))}
            <Part geo={target.geo} edges={target.edges} color={PART.target} opacity={s.parts} z={s.packZ} />
            <Part geo={bridge.geo} edges={bridge.edges} color={strapColor} opacity={s.parts * (1 - s.revised)} />
            <Part geo={revised.geo} edges={revised.edges} color={revisedColor} opacity={s.parts * s.revised} />
            {s.probe > 0 && (
              <mesh geometry={target.geo} position={[0, 0, s.probeZ]}>
                <meshStandardMaterial color={s.probeColor} transparent opacity={s.probe} depthWrite={false} />
              </mesh>
            )}
            {s.sweep >= 0 && (
              <mesh position={[-70 + 140 * s.sweep, -6, 33]}>
                <boxGeometry args={[4, 44, 18]} />
                <meshBasicMaterial color={C.cobalt} transparent opacity={0.28} depthWrite={false} />
              </mesh>
            )}
            {s.witness > 0 && (
              // Drawn over the strap that hides the contact point.
              <group position={[wx, wy, wz]} renderOrder={10}>
                <mesh renderOrder={10}>
                  <sphereGeometry args={[2.8, 24, 24]} />
                  <meshBasicMaterial color={C.signal} transparent opacity={s.witness} depthTest={false} />
                </mesh>
                <mesh scale={1 + s.pulse * 5} renderOrder={10}>
                  <torusGeometry args={[2.8, 0.45, 8, 48]} />
                  <meshBasicMaterial
                    color={C.signal}
                    transparent
                    opacity={s.witness * (1 - s.pulse)}
                    depthTest={false}
                  />
                </mesh>
              </group>
            )}
            {pathLength > 0.5 && (
              <group position={pathStart}>
                <mesh position={[0, 0, pathLength / 2]} rotation={[Math.PI / 2, 0, 0]}>
                  <cylinderGeometry args={[0.9, 0.9, pathLength, 12]} />
                  <meshBasicMaterial color={C.verified} />
                </mesh>
                <mesh position={[0, 0, pathLength + 3]} rotation={[Math.PI / 2, 0, 0]}>
                  <coneGeometry args={[3, 6, 16]} />
                  <meshBasicMaterial color={C.verified} />
                </mesh>
              </group>
            )}
          </group>
        </group>
      </group>
    </ThreeCanvas>
  )
}
