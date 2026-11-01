import { ContactShadows, Environment, Lightformer } from '@react-three/drei'
import { memo } from 'react'

/**
 * Procedural studio: softbox key, strip rim and floor bounce. No HDR download,
 * rendered once into the environment map so demand-mode canvases stay idle.
 */
export const Studio = memo(function Studio({ theme, shadow = true, polished = false, captureRevision = 0 }: { theme: 'light' | 'dark'; shadow?: boolean; polished?: boolean; captureRevision?: string | number }) {
  const dark = theme === 'dark'
  return <>
    <Lighting theme={theme} polished={polished} />
    {shadow && <ContactShadows position={[0, -0.021, 0]} scale={4.2} far={1.2} blur={2.6} opacity={dark ? 0.6 : 0.32} resolution={512} frames={1} color={dark ? '#000000' : '#2a2c2e'} userData={{ captureRevision }} />}
  </>
})

const Lighting = memo(function Lighting({ theme, polished }: { theme: 'light' | 'dark'; polished: boolean }) {
  const dark = theme === 'dark'
  return (
    <>
      <ambientLight intensity={dark ? 0.18 : 0.35} />
      <directionalLight position={[2.5, 4, 3]} intensity={dark ? 1.4 : 1.1} />
      <directionalLight position={[-3, 1.5, -2]} intensity={dark ? 0.9 : 0.35} color={dark ? '#9fb6ff' : '#ffffff'} />
      <Environment resolution={256} frames={1}>
        <color attach="background" args={[dark ? polished ? '#53627c' : '#0d0f10' : polished ? '#a9b8d1' : '#d9d8d3']} />
        {polished && <Lightformer form="rect" intensity={3} position={[-3, 3, 4]} rotation-y={Math.PI / 4} scale={[2, 5, 1]} color="#b4cdff" />}
        <Lightformer form="rect" intensity={dark ? 2.2 : 2.6} position={[0, 5, 0.5]} rotation-x={Math.PI / 2} scale={[8, 5, 1]} />
        <Lightformer form="rect" intensity={dark ? 1.6 : 2} position={[-5, 2, 2]} rotation-y={Math.PI / 2.6} scale={[5, 2.2, 1]} />
        <Lightformer form="rect" intensity={dark ? 2.4 : 1.4} position={[5, 1.2, -2.5]} rotation-y={-Math.PI / 2.4} scale={[6, 0.6, 1]} />
        <Lightformer form="rect" intensity={0.6} position={[0, -3, 0]} rotation-x={-Math.PI / 2} scale={[8, 8, 1]} color={dark ? '#30353a' : '#f2f1ed'} />
      </Environment>
    </>
  )
})
