import { readFileSync, writeFileSync, readdirSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'

// Retain the notices actually shipped with the locked production dependencies.
// The bundle also keeps upstream @license comments; this file supplies full texts.
const root = resolve(import.meta.dirname, '..')
const lock = JSON.parse(readFileSync(resolve(root, 'package-lock.json'), 'utf8'))
const sections = [
  'UNLOCK frontend third-party notices',
  'These dependencies retain their own licenses. The B02 CC BY 4.0 grant does not relicense software.',
]
let count = 0
for (const [directory, entry] of Object.entries(lock.packages).sort(([a], [b]) => a.localeCompare(b))) {
  if (!directory || entry.dev || !directory.startsWith('node_modules/')) continue
  const path = resolve(root, directory)
  if (!existsSync(resolve(path, 'package.json'))) continue // optional platform package
  const pkg = JSON.parse(readFileSync(resolve(path, 'package.json'), 'utf8'))
  const files = readdirSync(path).filter(name => /^(licen[cs]e|copying|notice)(\.|$)/i.test(name))
  sections.push(`\n${'='.repeat(72)}\n${pkg.name} ${pkg.version}\nLicense: ${typeof pkg.license === 'string' ? pkg.license : JSON.stringify(pkg.license ?? entry.license ?? 'See upstream package')}\n${pkg.homepage ?? pkg.repository?.url ?? ''}`)
  for (const file of files) sections.push(`\n${file}\n${readFileSync(resolve(path, file), 'utf8')}`)
  if (pkg.name === 'gsap') sections.push('Copyright 2008-2026, GreenSock. All rights reserved.\nSubject to https://gsap.com/standard-license')
  count += 1
}
writeFileSync(resolve(root, 'public/THIRD_PARTY_NOTICES.txt'), sections.join('\n') + '\n')
console.log(`Preserved notices for ${count} installed production dependencies.`)
