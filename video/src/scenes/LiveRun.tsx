import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion'
import { b05, live, stageAt, type LiveEvent } from '../data'
import { B05Model, type ModelState } from '../parts/B05Model'
import { C, PART, clamp, easeMech, easeOut, mono, sans } from '../theme'

// Real run seconds -> video seconds. The baseline (import and Stage A, no model)
// is compressed harder than the model's turns. The on-screen clock is real.
const MAP: [number, number][] = [
  [0, 1.2],
  [19.5, 4.4],
  [live.total_s, 24],
]
const REPLAY_END = MAP[MAP.length - 1][1]

function realAt(v: number) {
  if (v <= MAP[0][1]) return 0
  for (let i = 0; i < MAP.length - 1; i++) {
    const [r0, v0] = MAP[i]
    const [r1, v1] = MAP[i + 1]
    if (v <= v1) return r0 + ((v - v0) / (v1 - v0)) * (r1 - r0)
  }
  return live.total_s
}

function videoAt(r: number) {
  for (let i = 0; i < MAP.length - 1; i++) {
    const [r0, v0] = MAP[i]
    const [r1, v1] = MAP[i + 1]
    if (r <= r1) return v0 + ((r - r0) / (r1 - r0)) * (v1 - v0)
  }
  return REPLAY_END
}

const PROPOSED = stageAt('PROPOSED')
const CONSTRUCTED = stageAt('CONSTRUCTED')
const CHECKED = stageAt('CHECKED')
const [WX, WY, WZ] = b05.witness.point_mm
const fmt = (n: number) => (Math.abs(n) < 0.05 ? '0' : n.toFixed(1))

type Turn = Extract<LiveEvent, { kind: 'turn' }>
type Tool = Extract<LiveEvent, { kind: 'tool' }>

const turns = live.events.filter((e): e is Turn => e.kind === 'turn')
const tools = live.events.filter((e): e is Tool => e.kind === 'tool')
const baseline = live.events.find((e) => e.kind === 'baseline')!
const final = live.events.find((e) => e.kind === 'final')!

// Log blocks with estimated heights, so the list can scroll smoothly.
const NOTE_CHARS_PER_LINE = 50
type Block = { t: number; h: number; key: string }
const blocks: Block[] = [
  { t: baseline.t, h: 96, key: 'baseline' },
  ...turns.map((turn) => {
    const own = tools.filter((x) => x.turn === turn.turn)
    const lines = Math.ceil(turn.note.length / NOTE_CHARS_PER_LINE)
    return {
      t: turn.t,
      h: 40 + lines * 30 + own.reduce((h, x) => h + (x.parameters ? 76 : 42), 0) + 24,
      key: `turn${turn.turn}`,
    }
  }),
  { t: final.t, h: 120, key: 'final' },
]

export const LiveRun: React.FC = () => {
  const frame = useCurrentFrame()
  const { fps, width, height } = useVideoConfig()
  const v = frame / fps
  const r = realAt(v)
  const ev = (a: number, b: number, x = r, easing = easeOut) =>
    interpolate(x, [a, b], [0, 1], { ...clamp, easing })
  const vp = (a: number, b: number, easing = easeOut) =>
    interpolate(v, [a, b], [0, 1], { ...clamp, easing })

  const travel = b05.witness.travel_mm
  const baseProbe = r < 23
  const s: ModelState = {
    azimuth: interpolate(v, [0, 30], [-0.7, 0.3]),
    // Close in while the run plays; ease back to leave room for the lift.
    scale: interpolate(v, [REPLAY_END - 1, REPLAY_END + 0.6], [1.36, 1.2], { ...clamp, easing: easeOut }),
    y: interpolate(v, [REPLAY_END - 1, REPLAY_END + 0.6], [-0.16, -0.3], { ...clamp, easing: easeOut }),
    parts: vp(0, 0.8),
    probeZ: baseProbe ? travel * ev(2, 14, r, easeMech) : b05.removal.distance_mm * ev(60, 70.5, r, easeMech),
    probe: baseProbe
      ? 0.42 * ev(1, 2) * (1 - ev(19.5, 23))
      : 0.38 * ev(58, 59.5) * (1 - ev(71, 72.5)),
    probeColor: baseProbe ? PART.target : PART.candidate,
    strapTint: ev(13.5, 15.5),
    revised: ev(CONSTRUCTED, CONSTRUCTED + 1.5),
    checked: ev(CHECKED, CHECKED + 0.8),
    sweep: r >= PROPOSED && r < CONSTRUCTED ? (r - PROPOSED) / (CONSTRUCTED - PROPOSED) : -1,
    witness: ev(14, 15.2) * (1 - ev(PROPOSED, PROPOSED + 3)),
    pulse: (frame % 36) / 36,
    packZ: b05.removal.distance_mm * vp(REPLAY_END + 0.8, REPLAY_END + 3.4, easeMech),
    path: vp(REPLAY_END + 0.1, REPLAY_END + 1.1),
  }

  const caption =
    r < 14
      ? { text: 'Stage A: the planner tries to lift the pack straight out', color: C.ink2 }
      : r < 19.5
        ? { text: `Blocked. Exact contact with the strap at (${fmt(WX)}, ${fmt(WY)}, ${fmt(WZ)}) mm`, color: C.signal }
        : r < PROPOSED
          ? { text: 'Muse investigates the blocker, the allowed edits and the bounds', color: C.ink2 }
          : r < CONSTRUCTED
            ? { text: 'The trusted constructor builds Muse’s proposal', color: C.ink2 }
            : r < CHECKED
              ? { text: 'Independent verifier: rebuild, check, re-plan the way out', color: C.ink2 }
              : { text: 'Verified. Nothing cut: the strap moved 12 mm.', color: C.verified }

  const construct = tools.find((x) => x.tool === 'construct_candidate')!
  // While the proposal is built, the caption band carries Muse's own words.
  const rationale = ev(PROPOSED, PROPOSED + 0.8) * (1 - ev(CONSTRUCTED + 2, CONSTRUCTED + 3))

  // Smooth scroll: each block's height counts as it appears.
  const LOG_TOP = 250
  const LOG_HEIGHT = height - LOG_TOP - 60
  const shown = blocks.reduce((h, b) => h + b.h * vp(videoAt(b.t), videoAt(b.t) + 0.35), 0)
  const scroll = Math.max(0, shown - LOG_HEIGHT)
  const leftW = 1140
  const MODEL_TOP = 230
  const BAND = 190 // caption band under the model

  return (
    <AbsoluteFill style={{ background: C.paper }}>
      <div style={{ position: 'absolute', left: 0, top: MODEL_TOP, width: leftW, height: height - MODEL_TOP - BAND }}>
        <B05Model width={leftW} height={height - MODEL_TOP - BAND} s={s} />
      </div>

      {/* Header over the model */}
      <div style={{ position: 'absolute', left: 70, top: 64, opacity: vp(0, 0.6) }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ background: C.cobalt, color: '#fff', fontFamily: mono, fontSize: 22, padding: '6px 14px', letterSpacing: '0.1em' }}>
            LIVE RUN
          </span>
          <span style={{ fontFamily: sans, fontSize: 30, fontWeight: 600, color: C.ink }}>
            Muse Spark 1.3 · B05 battery bay
          </span>
        </div>
        <div style={{ fontFamily: mono, fontSize: 20, color: C.ink3, marginTop: 12 }}>
          {live.run_id} · 1 Nov 2026 · Meta Model API
        </div>
      </div>

      {/* Real clock */}
      <div style={{ position: 'absolute', left: 70, top: 168, fontFamily: mono, opacity: vp(0, 0.6) }}>
        <span style={{ fontSize: 46, color: C.ink }}>t = {r.toFixed(1)} s</span>
        <span style={{ fontSize: 20, color: C.ink3, marginLeft: 18 }}>real time · replayed ≈3× faster</span>
      </div>

      {/* Caption band: the phase, or Muse's rationale while its proposal is built */}
      <div
        style={{
          position: 'absolute',
          left: 70,
          bottom: 64,
          width: 1010,
          fontFamily: sans,
          fontSize: 34,
          fontWeight: 500,
          color: caption.color,
          opacity: vp(0.6, 1.2) * (1 - rationale),
        }}
      >
        {caption.text}
      </div>
      {rationale > 0 && (
        <div style={{ position: 'absolute', left: 70, bottom: 52, width: 1010, opacity: rationale }}>
          <div style={{ fontFamily: mono, fontSize: 19, color: C.ink3, letterSpacing: '0.08em' }}>
            THE CONSTRUCTOR BUILDS MUSE’S PROPOSAL · ITS RATIONALE, VERBATIM
          </div>
          <div style={{ fontFamily: mono, fontSize: 27, color: C.ink, marginTop: 10, lineHeight: 1.35 }}>
            “{construct.rationale}”
          </div>
        </div>
      )}

      {/* Decision log */}
      <div style={{ position: 'absolute', left: leftW, top: 0, width: width - leftW, height, borderLeft: `2px solid ${C.rule}`, background: C.paper2 }}>
        <div style={{ padding: '64px 48px 0', opacity: vp(0, 0.6) }}>
          <div style={{ fontFamily: mono, fontSize: 22, color: C.ink3, letterSpacing: '0.1em' }}>DECISION LOG</div>
          <div style={{ fontFamily: sans, fontSize: 28, color: C.ink2, marginTop: 10 }}>
            Every call is validated by the engine before it runs
          </div>
        </div>
        <div
          style={{
            position: 'absolute',
            top: LOG_TOP,
            left: 48,
            right: 40,
            height: LOG_HEIGHT,
            overflow: 'hidden',
            maskImage: 'linear-gradient(to bottom, transparent 0, black 48px)',
          }}
        >
          <div style={{ transform: `translateY(${-scroll}px)` }}>
            {blocks.map((b) => {
              const p = vp(videoAt(b.t), videoAt(b.t) + 0.35)
              if (p <= 0) return null
              return (
                <div key={b.key} style={{ height: b.h, opacity: p, transform: `translateX(${(1 - p) * 20}px)` }}>
                  <LogBlock id={b.key} r={r} v={v} />
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  )
}

const Time: React.FC<{ t: number }> = ({ t }) => (
  <span style={{ fontFamily: mono, fontSize: 20, color: C.ink3, width: 92, display: 'inline-block' }}>{t.toFixed(1)}s</span>
)

const LogBlock: React.FC<{ id: string; r: number; v: number }> = ({ id, r, v }) => {
  if (id === 'baseline') {
    return (
      <div>
        <Time t={baseline.t} />
        <span style={{ fontFamily: mono, fontSize: 24, color: C.ink }}>Stage A baseline</span>
        <div style={{ fontFamily: mono, fontSize: 22, color: C.signal, marginLeft: 92, marginTop: 8 }}>
          no supported path · target Z+ blocked
        </div>
      </div>
    )
  }
  if (id === 'final') {
    return (
      <div style={{ borderTop: `2px solid ${C.rule}`, paddingTop: 18 }}>
        <Time t={final.t} />
        <span style={{ fontFamily: mono, fontSize: 26, fontWeight: 500, color: C.verified }}>
          {final.kind === 'final' ? final.outcome : ''}
        </span>
        <div style={{ fontFamily: mono, fontSize: 20, color: C.ink3, marginLeft: 92, marginTop: 10 }}>
          {live.tool_calls} tool calls · {live.rejected_calls} refused · {live.total_s.toFixed(1)} s
        </div>
      </div>
    )
  }
  const turn = turns.find((x) => `turn${x.turn}` === id)!
  const own = tools.filter((x) => x.turn === turn.turn)
  const typed = Math.max(0, Math.floor((v - videoAt(turn.t)) * 60))
  return (
    <div>
      <Time t={turn.t} />
      <span style={{ fontFamily: mono, fontSize: 22, color: C.cobalt, letterSpacing: '0.06em' }}>TURN {turn.turn}</span>
      <div style={{ fontFamily: sans, fontStyle: 'italic', fontSize: 23, lineHeight: '30px', color: C.ink2, marginLeft: 92, marginTop: 6 }}>
        {turn.note.slice(0, typed)}
      </div>
      {own.map((x) => {
        const done = r >= x.t
        return (
          <div key={x.tool} style={{ marginLeft: 92, marginTop: 10 }}>
            <span style={{ fontFamily: mono, fontSize: 23, color: C.ink, background: '#fff', border: `1.5px solid ${C.rule}`, padding: '3px 10px' }}>
              {x.tool}
            </span>
            <span style={{ fontFamily: mono, fontSize: 21, color: done ? C.verified : C.ink3, marginLeft: 14 }}>
              {done ? '✓ ok' : 'running' + '.'.repeat(1 + (Math.floor(v * 3) % 3))}
            </span>
            {x.parameters && (
              <div style={{ fontFamily: mono, fontSize: 19, color: C.ink3, marginTop: 8 }}>
                offset_y {x.parameters.offset_y_mm} mm · cites {x.evidence_ids?.join(', ')}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
