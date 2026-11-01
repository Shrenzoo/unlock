import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion'
import { live } from '../data'
import { C, clamp, easeOut, mono, sans } from '../theme'

const LOCKED = ['shell', 'python', 'filesystem', 'web']

/** The model's entire reach: eight engineering tools, and nothing else. */
export const Tools: React.FC = () => {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const at = (sec: number, len = 0.5) =>
    interpolate(frame, [sec * fps, (sec + len) * fps], [0, 1], { ...clamp, easing: easeOut })
  const out = interpolate(frame, [5.4 * fps, 6 * fps], [1, 0], clamp)

  return (
    <AbsoluteFill style={{ background: C.paper, padding: '120px 160px', opacity: out }}>
      <div style={{ fontFamily: mono, fontSize: 26, color: C.ink3, letterSpacing: '0.08em', opacity: at(0.1) }}>
        MUSE SPARK 1.3 · META MODEL API
      </div>
      <div style={{ fontFamily: sans, fontSize: 88, fontWeight: 600, color: C.ink, marginTop: 18, opacity: at(0.3) }}>
        Eight tools. Nothing else.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 22, marginTop: 70 }}>
        {live.tools.map((tool, i) => {
          const p = at(0.9 + i * 0.12)
          const used = live.tools_used.includes(tool)
          return (
            <div
              key={tool}
              style={{
                opacity: p,
                transform: `translateY(${(1 - p) * 16}px)`,
                border: `2px solid ${C.ink}`,
                background: '#fff',
                padding: '24px 26px',
                fontFamily: mono,
                fontSize: 27,
                color: C.ink,
                display: 'flex',
                alignItems: 'center',
                gap: 14,
              }}
            >
              <span style={{ width: 12, height: 12, background: used ? C.cobalt : C.rule }} />
              {tool}
            </div>
          )
        })}
      </div>
      <div style={{ display: 'flex', gap: 22, marginTop: 56, alignItems: 'center', opacity: at(2.6) }}>
        <span style={{ fontFamily: sans, fontSize: 30, color: C.ink3, marginRight: 12 }}>Not available:</span>
        {LOCKED.map((x) => (
          <span
            key={x}
            style={{
              fontFamily: mono,
              fontSize: 27,
              color: C.ink3,
              border: `2px dashed ${C.rule}`,
              padding: '12px 22px',
              textDecoration: 'line-through',
            }}
          >
            {x}
          </span>
        ))}
      </div>
      <div style={{ fontFamily: sans, fontSize: 36, color: C.ink2, marginTop: 64, opacity: at(3.3) }}>
        <span style={{ display: 'inline-block', width: 14, height: 14, background: C.cobalt, marginRight: 14 }} />
        Called in the live run: {live.tools_used.length} of {live.tools.length}. The engine validates every call.
      </div>
    </AbsoluteFill>
  )
}
