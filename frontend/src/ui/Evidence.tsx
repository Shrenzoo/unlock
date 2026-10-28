import type { CheckResult, Provenance, ProvenanceKind } from '@/domain/types'
import './ui.css'

/**
 * Evidence presentation rules (PRD §16, §19):
 * - green appears only for a pass backed by computed evidence;
 * - an illustrative pass is drawn as an outline in ink, never green;
 * - every state has a glyph and words, so colour is never the only signal.
 */

export function Glyph({ kind }: { kind: CheckResult | 'pending' | 'running' }) {
  const common = { width: 14, height: 14, viewBox: '0 0 14 14', 'aria-hidden': true as const }
  switch (kind) {
    case 'pass':
      return (
        <svg {...common}>
          <path d="M3 7.2l2.6 2.6L11 4.4" fill="none" stroke="currentColor" strokeWidth="1.6" />
        </svg>
      )
    case 'fail':
      return (
        <svg {...common}>
          <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" stroke="currentColor" strokeWidth="1.6" />
        </svg>
      )
    case 'unknown':
      return (
        <svg {...common}>
          <path d="M5 5.2a2 2 0 113 1.7c-.6.4-1 .8-1 1.6M7 10.4v.2" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      )
    case 'running':
      return (
        <svg {...common} className="glyph-spin">
          <path d="M7 2a5 5 0 015 5" fill="none" stroke="currentColor" strokeWidth="1.6" />
        </svg>
      )
    case 'pending':
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="2" fill="currentColor" opacity=".5" />
        </svg>
      )
    default:
      return (
        <svg {...common}>
          <path d="M3.5 7h7" stroke="currentColor" strokeWidth="1.6" />
        </svg>
      )
  }
}

export function resultLabel(result: CheckResult, provenance: ProvenanceKind) {
  const computed = provenance !== 'illustrative'
  switch (result) {
    case 'pass':
      return { tone: computed ? 'verified' : 'pass-illustrative', text: computed ? 'Passed' : 'Pass (illustrative)' }
    case 'fail':
      return { tone: 'fail', text: computed ? 'Failed' : 'Fail (illustrative)' }
    case 'unknown':
      return { tone: 'unknown', text: 'Unknown' }
    default:
      return { tone: 'na', text: 'Not evaluated' }
  }
}

export function CheckResultTag({ result, provenance }: { result: CheckResult; provenance: ProvenanceKind }) {
  const { tone, text } = resultLabel(result, provenance)
  return (
    <span className={`result result--${tone}`}>
      <Glyph kind={result} />
      <span>{text}</span>
    </span>
  )
}

export function ProvenanceTag({ provenance, compact = false }: { provenance: Provenance; compact?: boolean }) {
  if (provenance.kind === 'illustrative') {
    return (
      <span className="prov prov--illustrative" title={provenance.note}>
        <span className="prov__swatch" aria-hidden="true" />
        {compact ? 'Illustrative' : 'Illustrative fixture, not computed'}
      </span>
    )
  }
  if (provenance.kind === 'computed_earlier') {
    return (
      <span className="prov prov--earlier" title={provenance.note}>
        <span className="prov__swatch" aria-hidden="true" />
        Computed earlier, <span className="mono">{provenance.input_hash}</span>
        {provenance.computed_at && <> at {new Date(provenance.computed_at).toLocaleString()}</>}
      </span>
    )
  }
  return (
    <span className="prov prov--live">
      <span className="prov__swatch" aria-hidden="true" />
      Live run
    </span>
  )
}
