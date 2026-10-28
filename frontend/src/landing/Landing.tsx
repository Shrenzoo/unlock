import { useEffect, useState } from 'react'
import { Link } from '@/router'
import { Logo, Mark } from '@/ui/Logo'
import { CheckResultTag, Glyph, ProvenanceTag } from '@/ui/Evidence'
import { FallbackDrawing } from '@/three/FallbackDrawing'
import { b02Candidates, b02Events, b02Run } from '@/fixtures/b02'
import { Hero } from './Hero'
import { Story } from './Story'
import { scrollToId, startSmoothScroll } from './scroll'
import './landing.css'

export default function Landing() {
  useEffect(() => startSmoothScroll(), [])

  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <Nav />
      <main id="main">
        <Hero />
        <Story />
        <WorkspacePreview />
        <Scope />
      </main>
      <Footer />
    </>
  )
}

const NAV_LINKS = [
  { id: 'story', label: 'How it works' },
  { id: 'workspace', label: 'Workspace' },
  { id: 'scope', label: 'Scope' },
]

function Nav() {
  const [dark, setDark] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const story = document.getElementById('story')
    const onScroll = () => {
      setScrolled(window.scrollY > 8)
      const r = story?.getBoundingClientRect()
      setDark(!!r && r.top <= 32 && r.bottom > 32)
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header className={`nav ${dark ? 'nav--dark' : ''} ${scrolled ? 'nav--solid' : ''}`}>
      <Link to="/" aria-label="UNLOCK home">
        <Logo tone={dark ? 'paper' : 'ink'} />
      </Link>
      <nav aria-label="Sections" className="nav__links">
        {NAV_LINKS.map((l) => (
          <a
            key={l.id}
            href={`#${l.id}`}
            onClick={(e) => {
              e.preventDefault()
              scrollToId(l.id)
            }}
          >
            {l.label}
          </a>
        ))}
      </nav>
      <Link to="/projects" className="nav__cta">
        Projects
      </Link>
    </header>
  )
}

const STAGE_LABELS: Record<string, string> = {
  inspect: 'Inspecting assembly',
  baseline: 'Searching removal paths',
  obstruction: 'Identifying obstruction',
  interventions: 'Evaluating supported modifications',
  construct: 'Constructing candidate',
  verify: 'Checking constraints',
  compare: 'Comparing repair paths',
}

function WorkspacePreview() {
  const checks = b02Candidates[1].verification!.checks.slice(0, 6)
  const stages = b02Events.filter((e) => e.state !== 'started' || e.stage === 'construct').slice(0, 7)

  return (
    <section id="workspace" className="preview" aria-labelledby="preview-title">
      <div className="preview__intro">
        <h2 id="preview-title">Then open it in the workspace.</h2>
        <p>
          The same module, as an engineer reviews it. The assembly tree, the viewport and the evidence panel stay in sync, and every stage of a redesign shows which tool ran and what it found.
        </p>
        <ul className="preview__list">
          <li>Pick the repair target in the tree or the viewport.</li>
          <li>Step to the failed move and inspect its witness.</li>
          <li>Read the proposal: template, parameters, protected regions.</li>
          <li>Compare original and revised paths side by side.</li>
        </ul>
        <Link to="/projects/prj_b02" className="btn btn--primary">
          <span className="btn__key" aria-hidden="true" />
          Open the sample project
        </Link>
      </div>

      <figure className="window" aria-label="Workspace layout using the B02 fixture">
        <div className="window__bar">
          <Mark size={16} />
          <span className="window__project">Trapped fan bridge</span>
          <span className="mono window__rev">Rev A</span>
          <span className="window__modes">
            {['Inspect', 'Analyze', 'Redesign', 'Compare', 'Export'].map((m) => (
              <span key={m} className={m === 'Redesign' ? 'is-active' : ''}>
                {m}
              </span>
            ))}
          </span>
          <ProvenanceTag provenance={b02Run.provenance} compact />
        </div>
        <div className="window__body">
          <ul className="window__tree mono" aria-label="Assembly tree">
            {['chassis', 'cover', 'bridge_bracket', 'fan_module', 'screw_f1', 'pcb_controller', 'screw_c1…c4', 'screw_b1, b2'].map((id) => (
              <li key={id} className={id === 'fan_module' ? 'is-target' : id === 'bridge_bracket' ? 'is-changed' : ''}>
                {id}
              </li>
            ))}
          </ul>
          <div className="window__view">
            <FallbackDrawing relief />
            <span className="window__viewlabel mono">Front section, candidate 2</span>
          </div>
          <div className="window__panel">
            <p className="window__heading">Redesign stages</p>
            <ol className="window__stages">
              {stages.map((e) => (
                <li key={e.sequence} className={e.state === 'failed' ? 'is-failed' : ''}>
                  <Glyph kind={e.state === 'failed' ? 'fail' : 'pass'} />
                  <span>{STAGE_LABELS[e.stage]}</span>
                  {e.tool && <span className="mono">{e.tool.name}</span>}
                </li>
              ))}
            </ol>
            <p className="window__heading">Constraint checks, candidate 2</p>
            <ul className="window__checks">
              {checks.map((c) => (
                <li key={c.constraint_id}>
                  <span>{c.label}</span>
                  <CheckResultTag result={c.result} provenance={b02Run.provenance.kind} />
                </li>
              ))}
            </ul>
          </div>
        </div>
        <figcaption>Illustrative fixture data. Checks are drawn in outline until the verifier produces a report.</figcaption>
      </figure>
    </section>
  )
}

function Scope() {
  return (
    <section id="scope" className="scope" aria-labelledby="scope-title">
      <h2 id="scope-title">What a pass means here.</h2>
      <p className="scope__lede">
        A pass is a geometry result for one target under one stated policy. It is evidence for a design review, not a manufacturing release.
      </p>
      <div className="scope__cols">
        <div>
          <h3>Checked under policy v1</h3>
          <ul>
            <li>Fixed components and placements unchanged</li>
            <li>Mounting pads and hole axes within 0.01 mm</li>
            <li>Design envelope and declared keep-outs</li>
            <li>Assembled collisions, declared contacts only</li>
            <li>Straight tool approach to every fastener</li>
            <li>Removal and reverse insertion along checked axis-aligned segments</li>
          </ul>
        </div>
        <div>
          <h3>Not assessed</h3>
          <ul className="scope__out">
            <li>Strength, stiffness and fatigue</li>
            <li>Electrical safety and shielding</li>
            <li>Manufacturing feasibility</li>
            <li>Restored product function</li>
            <li>Torque, forces, cables, clips and adhesives</li>
          </ul>
        </div>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer className="footer">
      <div className="footer__close">
        <p className="footer__line">Make replacement a design decision.</p>
        <Link to="/projects/prj_b02" className="btn btn--paper">
          <span className="btn__key" aria-hidden="true" />
          Open the sample assembly
        </Link>
      </div>
      <div className="footer__meta">
        <Logo tone="paper" />
        <p>
          A prototype for the Meta Global AI Developer Hackathon, 2026. Redesign proposals are planned to come from Muse Spark Open through bounded tool calls; the model and geometry services are not connected in this build.
        </p>
        <p>Fixture B02 is synthetic and authored by the team. Every result shown on this site is illustrative.</p>
      </div>
    </footer>
  )
}
