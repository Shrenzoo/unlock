import { interpolate } from 'remotion'
import { C } from '../theme'

/**
 * The product mark (frontend/src/ui/Logo.tsx): a bridge bracket with a relief in
 * its web, and the cobalt service part leaving through it. `bracket` slides the
 * halves together; `lift` raises the part from inside the bracket to its exit.
 */
export const Mark: React.FC<{ size: number; bracket: number; lift: number; color?: string }> = ({
  size,
  bracket,
  lift,
  color = C.ink,
}) => {
  const spread = (1 - bracket) * 5
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={{ overflow: 'visible' }}>
      <path d="M2 22V11h7v3H5v8z" fill={color} opacity={bracket} transform={`translate(${-spread} 0)`} />
      <path d="M22 22V11h-7v3h4v8z" fill={color} opacity={bracket} transform={`translate(${spread} 0)`} />
      <rect
        x={9.5}
        y={interpolate(lift, [0, 1], [16, 2])}
        width={5}
        height={5}
        fill={C.cobalt}
        opacity={lift > 0 ? 1 : 0}
      />
    </svg>
  )
}
