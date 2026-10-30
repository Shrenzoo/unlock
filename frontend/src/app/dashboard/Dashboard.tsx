import { useEffect, useRef, useState, type DragEvent } from 'react'
import { api, ServiceNotConnected, validatePackage } from '@/api'
import type { ProjectSummary, StageEvent } from '@/domain/types'
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
  const [connection, setConnection] = useState<'checking' | 'connected' | 'unreachable'>('checking')
  const [dragging, setDragging] = useState(false)
  const [readOnly, setReadOnly] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let live = true
    let recorded = false
    api.health().then((h) => { recorded = h?.access === 'read_only'; if (live) setReadOnly(recorded) }).catch(() => {})
    // A failed refresh is a connection problem, never a package problem, and never
    // a reason to show example data instead.
    const refresh = () => api.listProjects()
      .then((p) => { if (live) { setProjects(p); setConnection('connected') } })
      .catch(() => { if (live) setConnection('unreachable') })
    void refresh()
    const timer = window.setInterval(() => { if (api.mode === 'http' && !recorded) void refresh() }, 2000)
    return () => {
      live = false
      window.clearInterval(timer)
    }
  }, [])

  async function accept(files: File[]) {
    if (readOnly) return
    const errors = validatePackage(files)
    if (errors.length) return setUpload({ kind: 'invalid', errors })
    try {
      const result = await api.importPackage(files)
      const controller = new AbortController()
      let projectId: string | undefined
      await api.streamEvents(result.job_id, (event) => { projectId = (event as StageEvent & { project_id?: string }).project_id ?? projectId }, controller.signal)
      setProjects(await api.listProjects())
      if (projectId) navigate(`/projects/${encodeURIComponent(projectId)}`)
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
        <span className="appbar__mode mono" data-connection={api.mode === 'fixture' ? 'fixture' : connection}>
          {api.mode === 'fixture' ? 'Fixture mode, bundled examples only' : connection === 'connected' ? readOnly ? 'Read-only engineering demonstration' : 'Connected to the engineering service' : connection === 'unreachable' ? 'Engine unreachable' : 'Connecting…'}
        </span>
      </header>

      <main className="dash__main">
        <section className="dash__projects" aria-labelledby="projects-title">
          <h1 id="projects-title">Projects</h1>
          <p className="dash__lede">Open a supported assembly to define a repair target and review a bounded redesign.</p>
          {connection === 'unreachable' && (
            <div className="notice notice--fail" role="alert" data-testid="connection-error">
              <p className="notice__title">
                <Glyph kind="fail" /> Cannot reach the UNLOCK engineering service
              </p>
              <p>
                No response from <span className="mono">{api.origin}</span>. Start the backend (<span className="mono">python -m unlock_engine.api</span>) and this page reconnects on its own. {projects ? 'The list below is from the last successful response.' : 'No example data is shown in its place.'}
              </p>
            </div>
          )}

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
                  <td colSpan={6} className="ptable__loading" aria-busy={connection === 'checking'}>
                    {connection === 'unreachable' ? 'No projects: the engineering service is not reachable.' : 'Loading projects…'}
                  </td>
                </tr>
              )}
              {projects?.map((p) => {
                const ready = p.status === 'ready'
                return (
                  <tr key={p.id} className={ready ? 'is-ready' : 'is-disabled'} onClick={ready ? () => navigate(`/projects/${encodeURIComponent(p.id)}`) : undefined}>
                    <td className="mono">{p.fixture_code}</td>
                    <td>
                      <span className="ptable__name">{p.name}</span>
                      <span className="ptable__desc">{p.description}</span>
                    </td>
                    <td className="num mono">{p.occurrences ?? '—'}</td>
                    <td className="mono">{p.revision?.slice(0, 12) ?? '—'}</td>
                    <td>{ready ? <span className="tag tag--hatched">{p.provenance === 'illustrative' ? 'Illustrative' : 'Computed CAD'}</span> : <span className="tag">{api.mode === 'http' ? 'Not ready yet' : 'Not authored yet'}</span>}</td>
                    <td className="ptable__action">
                      {ready ? (
                        <Link to={`/projects/${encodeURIComponent(p.id)}`} className="btn btn--primary btn--sm" onClick={(e) => e.stopPropagation()}>
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
          <p className="dash__foot">{readOnly ? 'B02 uses a real synthetic STEP assembly and previously computed verification evidence. Public access is read-only; it runs no CAD jobs or model inference.' : api.mode === 'http' ? 'B01, B02 and B03 use generated synthetic STEP assemblies. Loading and analysis execute on the connected backend.' : 'Illustrative mode uses prepared UI records; it performs no engineering computation.'}</p>
        </section>

        <aside className="dash__side" aria-label="Import a package">
          <h2>Import a package</h2>
          {readOnly && <p role="status">Uploads are disabled in this public demonstration. Engineering jobs require authenticated access.</p>}
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
            <button type="button" className="btn btn--quiet btn--sm" disabled={readOnly} onClick={() => input.current?.click()}>
              Choose files
            </button>
            <input
              ref={input}
              type="file"
              disabled={readOnly}
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
