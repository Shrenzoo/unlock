import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion'
import { gallery } from '../data'
import { C, clamp, easeOut, mono, sans } from '../theme'

// The site's own wording for each recorded outcome (Projects table).
const VERDICT: Record<string, { label: string; glyph: string; color: string; wash: string }> = {
  VERIFIED_IMPROVEMENT_FOUND: { label: 'Verified improvement', glyph: '✓', color: C.verified, wash: C.verifiedWash },
  INCOMPLETE_ANALYSIS: { label: 'Not proven, no claim made', glyph: '?', color: C.ink2, wash: C.paper2 },
  NO_SUPPORTED_CANDIDATE: { label: 'No supported candidate', glyph: '–', color: C.ink2, wash: C.paper2 },
  NO_VERIFIED_IMPROVEMENT: { label: 'No verified improvement', glyph: '–', color: C.ink2, wash: C.paper2 },
}

/** Six assemblies, six recorded answers, refusals included. */
export const Answers: React.FC = () => {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const at = (sec: number, len = 0.45) =>
    interpolate(frame, [sec * fps, (sec + len) * fps], [0, 1], { ...clamp, easing: easeOut })

  return (
    <AbsoluteFill style={{ background: C.paper, padding: '90px 120px' }}>
      <div style={{ fontFamily: sans, fontSize: 76, fontWeight: 600, color: C.ink, opacity: at(0.1) }}>
        Six assemblies. Six different answers.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 28, marginTop: 56 }}>
        {gallery.map((g, i) => {
          const card = at(0.6 + i * 0.35)
          const stamp = at(1.0 + i * 0.35, 0.3)
          const v = VERDICT[g.outcome] ?? { label: g.outcome, glyph: '·', color: C.ink2, wash: C.paper2 }
          return (
            <div
              key={g.code}
              style={{
                background: '#fff',
                // B05 is the assembly the live run just fixed.
                border: `2px solid ${g.code === 'B05' ? C.cobalt : C.rule}`,
                padding: '28px 30px',
                height: 330,
                display: 'flex',
                flexDirection: 'column',
                opacity: card,
                transform: `translateY(${(1 - card) * 18}px)`,
              }}
            >
              <div style={{ fontFamily: mono, fontSize: 24, color: C.ink3 }}>{g.code}</div>
              <div style={{ fontFamily: sans, fontSize: 34, fontWeight: 600, color: C.ink, marginTop: 8 }}>{g.name}</div>
              <div style={{ fontFamily: sans, fontSize: 23, color: C.ink2, marginTop: 10, lineHeight: 1.3 }}>
                {g.description ?? 'The original licensed demonstration'}
              </div>
              <div style={{ flex: 1 }} />
              <div
                style={{
                  alignSelf: 'flex-start',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  border: `2px solid ${v.color}`,
                  background: v.wash,
                  color: v.color,
                  fontFamily: sans,
                  fontWeight: 600,
                  fontSize: 26,
                  padding: '8px 16px',
                  opacity: stamp,
                  transform: `scale(${1.1 - 0.1 * stamp})`,
                }}
              >
                <span style={{ fontFamily: mono }}>{v.glyph}</span>
                {v.label}
              </div>
            </div>
          )
        })}
      </div>
      <div style={{ fontFamily: sans, fontSize: 44, color: C.ink, marginTop: 50, opacity: at(3.4, 0.6) }}>
        When UNLOCK can’t prove a fix, it says so.
      </div>
    </AbsoluteFill>
  )
}
