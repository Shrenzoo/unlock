import { useEffect, useRef, useState, type DragEvent } from 'react'
import { api, ServiceNotConnected, validatePackage } from '@/api'
import type { ProjectSummary } from '@/domain/types'
import { Link, navigate } from '@/router'
import { Logo } from '@/ui/Logo'
import { Glyph } from '@/ui/Evidence'
import './dashboard.css'

type UploadState =
  | { kind: 'idle' }
  | { kind: 'invalid'; errors: Array<{ field: string; message: string }> }
  | { kind: 'unavailable'; files: string[] }

export default function Dashboard() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null)
  const [upload, setUpload] = useState<UploadState>({ kind: 'idle' })
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let live = true
    api.listProjects().then((p) => live && setProjects(p))
    return () => {
      live = false
    }
  }, [])

  async function accept(files: File[]) {
    const errors = validatePackage(files)
    if (errors.length) return setUpload({ kind: 'invalid', errors })
    try {
      await api.importPackage(files)
    } catch (e) {
      if (e instanceof ServiceNotConnected) setUpload({ kind: 'unavailable', files: files.map((f) => f.name) })
      else setUpload({ kind: 'invalid', errors: [{ field: 'import', message: (e as Error).message }] })
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    accept(Array.from(e.dataTransfer.files))
  }

  return (
    <div className="dash">
      <header className="appbar">
        <Link to="/" aria-label="UNLOCK home">
          <Logo />
        </Link>
        <span className="appbar__crumb">Projects</span>
        <span className="appbar__mode mono">{api.mode === 'fixture' ? 'Fixture mode, bundled examples only' : 'Connected'}</span>
      </header>

      <main className="dash__main">
        <section className="dash__projects" aria-labelledby="projects-title">
          <h1 id="projects-title">Projects</h1>
          <p className="dash__lede">Open a supported assembly to define a repair target and review a bounded redesign.</p>

          <table className="ptable">
            <thead>
              <tr>
                <th scope="col">Fixture</th>
                <th scope="col">Assembly</th>
                <th scope="col" className="num">
                  Parts
                </th>
                <th scope="col">Revision</th>
                <th scope="col">Data</th>
                <th scope="col">
                  <span className="visually-hidden">Action</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {projects === null && (
                <tr>
                  <td colSpan={6} className="ptable__loading">
                    Loading projects…
                  </td>
                </tr>
              )}
              {projects?.map((p) => {
                const ready = p.status === 'ready'
                return (
                  <tr key={p.id} className={ready ? 'is-ready' : 'is-disabled'} onClick={ready ? () => navigate(`/projects/${p.id}`) : undefined}>
                    <td className="mono">{p.fixture_code}</td>
                    <td>
                      <span className="ptable__name">{p.name}</span>
                      <span className="ptable__desc">{p.description}</span>
                    </td>
                    <td className="num mono">{p.occurrences ?? '—'}</td>
                    <td className="mono">{p.revision ?? '—'}</td>
                    <td>{ready ? <span className="tag tag--hatched">Illustrative</span> : <span className="tag">Not authored yet</span>}</td>
                    <td className="ptable__action">
                      {ready ? (
                        <Link to={`/projects/${p.id}`} className="btn btn--primary btn--sm" onClick={(e) => e.stopPropagation()}>
                          Open
                        </Link>
                      ) : (
                        <span className="ptable__na">Unavailable</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="dash__foot">B01 and B03 are specified in the PRD evaluation plan and will appear here once the team authors their geometry.</p>
        </section>

        <aside className="dash__side" aria-label="Import a package">
          <h2>Import a package</h2>
          <div
            className={`drop ${dragging ? 'is-over' : ''}`}
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <svg width="40" height="40" viewBox="0 0 40 40" aria-hidden="true" className="drop__icon">
              <path d="M4 36V16h10v6H10v14zM36 36V16H26v6h4v14z" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <path d="M20 4v16M14 10l6-6 6 6" fill="none" stroke="currentColor" strokeWidth="1.5" />
            </svg>
            <p>Drop a ZIP, or a STEP file with its manifest.json</p>
            <button type="button" className="btn btn--quiet btn--sm" onClick={() => input.current?.click()}>
              Choose files
            </button>
            <input
              ref={input}
              type="file"
              multiple
              accept=".zip,.step,.stp,.json"
              className="visually-hidden"
              tabIndex={-1}
              onChange={(e) => accept(Array.from(e.target.files ?? []))}
            />
          </div>

          {upload.kind === 'invalid' && (
            <div className="notice notice--fail" role="alert">
              <p className="notice__title">
                <Glyph kind="fail" /> Package not accepted
              </p>
              <ul>
                {upload.errors.map((er, i) => (
                  <li key={i}>
                    <span className="mono">{er.field}</span> {er.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {upload.kind === 'unavailable' && (
            <div className="notice" role="status">
              <p className="notice__title">
                <Glyph kind="unknown" /> Import service not connected
              </p>
              <p>
                <span className="mono">{upload.files.join(', ')}</span> passed the local package checks. Parsing STEP needs the engineering service, which this build does not include. Nothing was uploaded and no project was created.
              </p>
            </div>
          )}

          <h3>Supported assemblies</h3>
          <dl className="spec">
            <dt>Geometry</dt>
            <dd>STEP AP214 or AP242, separate closed solids</dd>
            <dt>Manifest</dt>
            <dd>manifest.json with roles, connections, tools and constraints</dd>
            <dt>Parts</dt>
            <dd>5 to 12 rigid occurrences, fasteners included</dd>
            <dt>Frame</dt>
            <dd>Millimetres, right-handed, Z up</dd>
            <dt>Motion</dt>
            <dd>Axis-aligned translations only</dd>
            <dt>Size</dt>
            <dd>25 MB compressed, 100 MB expanded</dd>
            <dt>Rejected</dt>
            <dd>Meshes, native CAD files, fused single bodies, flexible parts</dd>
          </dl>
        </aside>
      </main>
    </div>
  )
}
