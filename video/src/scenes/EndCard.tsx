import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion'
import { Mark } from '../parts/Mark'
import { C, clamp, easeMech, easeOut, mono, sans } from '../theme'

export const EndCard: React.FC = () => {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const at = (sec: number, len = 0.6, ease = easeOut) =>
    interpolate(frame, [sec * fps, (sec + len) * fps], [0, 1], { ...clamp, easing: ease })

  return (
    <AbsoluteFill style={{ background: C.paper, alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ fontFamily: sans, fontSize: 64, color: C.ink2, opacity: at(0.2) }}>Every battery wears out.</div>
      <div style={{ fontFamily: sans, fontSize: 96, fontWeight: 600, color: C.ink, marginTop: 10, opacity: at(0.9) }}>
        Design for the day it does.
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 24, marginTop: 90, opacity: at(1.8) }}>
        <Mark size={72} bracket={at(1.8)} lift={at(2.2, 0.7, easeMech)} />
        <span style={{ fontFamily: sans, fontWeight: 600, fontSize: 58, letterSpacing: '0.14em', color: C.ink }}>
          UNLOCK
        </span>
      </div>
      <div style={{ fontFamily: mono, fontSize: 30, color: C.ink, marginTop: 34, opacity: at(2.6) }}>
        unlock-labs.pages.dev
      </div>
      <div style={{ fontFamily: sans, fontSize: 28, color: C.ink3, marginTop: 18, opacity: at(3.0) }}>
        Built with Muse Spark 1.3 on the Meta Model API · Judge access on Projects
      </div>
    </AbsoluteFill>
  )
}
