/**
 * Front elevation of fixture B02 as a static drawing, used when WebGL is not
 * available. Same millimetre dimensions as the 3D presentation geometry.
 */
export function FallbackDrawing({ relief = false, className }: { relief?: boolean; className?: string }) {
  // x: -80..80 → 0..320, z: 0..64 → 150..22 (scale 2)
  const X = (x: number) => (x + 80) * 2 + 20
  const Z = (z: number) => 160 - z * 2
  return (
    <svg viewBox="0 0 360 190" className={className} role="img" aria-label="Front section of the B02 module: chassis, cover, bridge bracket over the fan module">
      <g fill="none" stroke="currentColor" strokeWidth="1">
        <rect x={X(-80)} y={Z(4)} width={320} height={8} />
        <rect x={X(-80)} y={Z(58)} width={6} height={108} />
        <rect x={X(77)} y={Z(58)} width={6} height={108} />
        <rect x={X(-80)} y={Z(61)} width={320} height={6} strokeDasharray="4 3" />
        <rect x={X(-56)} y={Z(8)} width={32} height={8} />
        <rect x={X(40)} y={Z(8)} width={32} height={8} />
        <rect x={X(-46)} y={Z(38)} width={12} height={60} />
        <rect x={X(40)} y={Z(38)} width={12} height={60} />
        {relief ? (
          <>
            <rect x={X(-46)} y={Z(42)} width={40} height={8} />
            <rect x={X(26)} y={Z(42)} width={40} height={8} />
          </>
        ) : (
          <rect x={X(-46)} y={Z(42)} width={184} height={8} stroke="var(--signal)" />
        )}
      </g>
      <rect x={X(-15)} y={Z(36)} width={60} height={60} fill="var(--cobalt)" opacity="0.9" />
      <g fontFamily="var(--font-mono)" fontSize="9" fill="currentColor">
        <text x={X(-15)} y={Z(36) - 6}>fan_module</text>
        <text x={X(48)} y={Z(42) - 6}>bridge_bracket</text>
      </g>
    </svg>
  )
}
