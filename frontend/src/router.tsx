import { useSyncExternalStore, type AnchorHTMLAttributes, type MouseEvent } from 'react'

/** Minimal history router: three routes do not justify a routing dependency. */

const listeners = new Set<() => void>()
const subscribe = (fn: () => void) => {
  listeners.add(fn)
  window.addEventListener('popstate', fn)
  return () => {
    listeners.delete(fn)
    window.removeEventListener('popstate', fn)
  }
}
const snapshot = () => window.location.pathname + window.location.search + window.location.hash

export function navigate(to: string, opts: { replace?: boolean } = {}) {
  if (to === snapshot()) return
  if (opts.replace) window.history.replaceState(null, '', to)
  else window.history.pushState(null, '', to)
  listeners.forEach((l) => l())
  if (!to.includes('#')) window.scrollTo(0, 0)
}

export function useLocation() {
  const href = useSyncExternalStore(subscribe, snapshot, snapshot)
  const url = new URL(href, window.location.origin)
  return { pathname: url.pathname, search: url.searchParams, hash: url.hash }
}

export type Route =
  | { name: 'landing' }
  | { name: 'projects' }
  | { name: 'workspace'; projectId: string }
  | { name: 'not_found' }

export function matchRoute(pathname: string): Route {
  if (pathname === '/' || pathname === '') return { name: 'landing' }
  if (pathname === '/projects') return { name: 'projects' }
  const m = pathname.match(/^\/projects\/([^/]+)$/)
  if (m) { try { return { name: 'workspace', projectId: decodeURIComponent(m[1]) } } catch { return { name: 'not_found' } } }
  return { name: 'not_found' }
}

export function Link({ to, onClick, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  const handle = (e: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(e)
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    e.preventDefault()
    navigate(to)
  }
  return <a href={to} onClick={handle} {...rest} />
}
