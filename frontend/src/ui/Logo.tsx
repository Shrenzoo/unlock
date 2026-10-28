import './ui.css'

/**
 * The mark is the product's one idea drawn as a part: a bridge bracket with a
 * relief cut in its web, and the service part (cobalt) leaving through it.
 */
export function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M2 22V11h7v3H5v8zM22 22V11h-7v3h4v8z" fill="currentColor" />
      <rect x="9.5" y="2" width="5" height="5" fill="var(--cobalt)" />
    </svg>
  )
}

export function Logo({ tone = 'ink' }: { tone?: 'ink' | 'paper' }) {
  return (
    <span className={`logo logo--${tone}`}>
      <Mark />
      <span className="logo__word">UNLOCK</span>
    </span>
  )
}
