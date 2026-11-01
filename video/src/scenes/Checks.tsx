import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion'
import { live } from '../data'
import { C, clamp, easeOut, mono, sans } from '../theme'

const LABELS: Record<string, string> = {
  integrity: 'Package integrity',
  solid_validity: 'Closed, valid solids',
  trusted_reconstruction: 'Independent rebuild matches',
  actual_change: `Real change: ${live.changed_volume_mm3.toLocaleString('en-US')} mm³`,
  protected_interfaces: 'Protected interfaces untouched',
  hole_geometry: 'Hole geometry unchanged',
  fixed_components: 'Every other part unchanged',
  placements: 'Placements unchanged',
  design_envelope: 'Inside the design envelope',
  keep_outs: 'Keep-out zones clear',
  assembled_intersections: 'No new collisions',
  target_path: 'The pack’s way out is clear',
}

/** The live run's revised-plan checks, ticked in order; green only for a pass. */
export const Checks: React.FC = () => {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const at = (sec: number, len = 0.35) =>
    interpolate(frame, [sec * fps, (sec + len) * fps], [0, 1], { ...clamp, easing: easeOut })
  const step = live.plan_steps[0]
  const lastTick = 1.0 + live.checks.length * 0.28
  const verdict = at(lastTick + 1.1, 0.5)

  return (
    <AbsoluteFill style={{ background: C.paper, padding: '100px 150px' }}>
      <div style={{ fontFamily: mono, fontSize: 24, color: C.ink3, letterSpacing: '0.1em', opacity: at(0) }}>
        INDEPENDENT VERIFICATION · LIVE RUN
      </div>
      <div style={{ fontFamily: sans, fontSize: 70, fontWeight: 600, color: C.ink, marginTop: 14, opacity: at(0.2) }}>
        The model’s opinion counts for nothing.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 70, rowGap: 20, marginTop: 60 }}>
        {live.checks.map((c, i) => {
          const p = at(1.0 + i * 0.28)
          const pass = c.result === 'pass'
          return (
            <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 20, opacity: 0.25 + 0.75 * p }}>
              <span
                style={{
                  width: 40,
                  height: 40,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  border: `2px solid ${p > 0.5 ? (pass ? C.verified : C.signal) : C.rule}`,
                  background: p > 0.5 ? (pass ? C.verifiedWash : C.signalWash) : 'transparent',
                  color: pass ? C.verified : C.signal,
                  fontFamily: mono,
                  fontSize: 26,
                }}
              >
                {p > 0.5 ? (pass ? '✓' : '×') : ''}
              </span>
              <span style={{ fontFamily: sans, fontSize: 34, color: C.ink }}>{LABELS[c.id] ?? c.id}</span>
            </div>
          )
        })}
      </div>
      <div style={{ fontFamily: mono, fontSize: 28, color: C.ink2, marginTop: 56, opacity: at(lastTick + 0.3, 0.5) }}>
        Re-planned from scratch: {step.component_id === 'target' ? 'pack' : step.component_id} lifts {step.axis}{' '}
        {step.distance_mm} mm · replay {live.replay} · reverse insertion {live.reverse}
      </div>
      <div
        style={{
          position: 'absolute',
          right: 150,
          bottom: 100,
          border: `4px solid ${C.verified}`,
          color: C.verified,
          fontFamily: mono,
          fontSize: 44,
          fontWeight: 500,
          letterSpacing: '0.08em',
          padding: '16px 30px',
          opacity: verdict,
          transform: `scale(${1.08 - 0.08 * verdict})`,
        }}
      >
        VERIFIED IMPROVEMENT
      </div>
    </AbsoluteFill>
  )
}
