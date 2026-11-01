import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion'
import { Mark } from '../parts/Mark'
import { C, clamp, easeMech, easeOut, sans } from '../theme'

/** The mark assembles, the service part rises out through the relief, then the name. */
export const Title: React.FC = () => {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const s = (a: number, b: number, ease = easeOut) =>
    interpolate(frame, [a * fps, b * fps], [0, 1], { ...clamp, easing: ease })
  const bracket = s(0.2, 1.0)
  const lift = s(1.0, 1.9, easeMech)
  const word = s(1.8, 2.6)
  const tag = s(2.6, 3.4)
  const rule = s(2.4, 3.4)
  const out = interpolate(frame, [4.4 * fps, 5 * fps], [1, 0], clamp)

  return (
    <AbsoluteFill style={{ background: C.paper, alignItems: 'center', justifyContent: 'center', opacity: out }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 44 }}>
        <Mark size={190} bracket={bracket} lift={lift} />
        <div
          style={{
            fontFamily: sans,
            fontWeight: 600,
            fontSize: 150,
            letterSpacing: '0.14em',
            color: C.ink,
            opacity: word,
            transform: `translateX(${(1 - word) * -24}px)`,
          }}
        >
          UNLOCK
        </div>
      </div>
      <div style={{ width: 760 * rule, height: 2, background: C.rule, marginTop: 56 }} />
      <div
        style={{
          fontFamily: sans,
          fontSize: 52,
          color: C.ink2,
          marginTop: 40,
          opacity: tag,
          transform: `translateY(${(1 - tag) * 14}px)`,
        }}
      >
        Design for the day it breaks.
      </div>
    </AbsoluteFill>
  )
}
