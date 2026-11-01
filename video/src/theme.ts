import { loadFont as loadMono } from '@remotion/google-fonts/IBMPlexMono'
import { loadFont as loadSans } from '@remotion/google-fonts/InstrumentSans'
import { Easing } from 'remotion'

// The site's tokens (frontend/src/styles/tokens.css). Colour carries function:
// cobalt = target, signal = obstruction, verified = a check that passed.
export const C = {
  paper: '#f2f1ed',
  paper2: '#e8e7e2',
  rule: '#cbc9c2',
  ink: '#17191b',
  ink2: '#4f5357',
  ink3: '#74787c',
  cobalt: '#3268f5',
  cobaltWash: '#dde5fb',
  signal: '#e4602f',
  signalWash: '#f8e1d6',
  verified: '#34866b',
  verifiedWash: '#dcebe4',
}

// The 3D viewport's part tones (frontend/src/app/workspace/LiveViewport.tsx).
export const PART = {
  neutral: '#aeb5b6',
  electronics: '#8a9390',
  fastener: '#cdd2d4',
  target: '#4287b4',
  obstacle: '#c78a28',
  candidate: '#6b9baf',
  checked: '#6a9b7a',
}

export const sans = loadSans('normal', {
  weights: ['400', '500', '600', '700'],
  subsets: ['latin'],
}).fontFamily
export const mono = loadMono('normal', {
  weights: ['400', '500'],
  subsets: ['latin'],
}).fontFamily

// Motion: precise, no overshoot.
export const easeOut = Easing.bezier(0.22, 1, 0.36, 1)
export const easeMech = Easing.bezier(0.7, 0, 0.2, 1)

export const FPS = 30
export const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const
