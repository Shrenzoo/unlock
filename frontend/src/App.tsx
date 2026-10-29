import { lazy, Suspense, useEffect } from 'react'
import { Link, matchRoute, useLocation } from './router'

const Landing = lazy(() => import('./landing/Landing'))
const Dashboard = lazy(() => import('./app/dashboard/Dashboard'))
const Workspace = lazy(() => import('./app/workspace/Workspace'))

const TITLES = {
  landing: 'UNLOCK — design for the day it breaks',
  projects: 'Projects — UNLOCK',
  workspace: 'Workspace — UNLOCK',
  not_found: 'Not found — UNLOCK',
}

export function App() {
  const { pathname } = useLocation()
  const route = matchRoute(pathname)

  useEffect(() => {
    document.title = TITLES[route.name]
  }, [route.name])

  return (
    <Suspense fallback={<div className="route-loading" aria-busy="true" />}>
      {route.name === 'landing' && <Landing />}
      {route.name === 'projects' && <Dashboard />}
      {route.name === 'workspace' && <Workspace key={route.projectId} projectId={route.projectId} />}
      {route.name === 'not_found' && (
        <main className="not-found">
          <p className="mono">404</p>
          <h1>No page at {pathname}</h1>
          <Link to="/" className="btn btn--quiet">
            Back to UNLOCK
          </Link>
        </main>
      )}
    </Suspense>
  )
}
