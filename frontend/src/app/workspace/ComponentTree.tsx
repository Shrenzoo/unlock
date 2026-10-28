import { memo, useMemo, useRef, useState, type Dispatch, type KeyboardEvent } from 'react'
import type { AssemblyManifest, Component } from '@/domain/types'
import { isPartId, type PartId } from '@/three/ModuleAssembly'
import type { Action } from './model'

interface Row {
  c: Component
  level: number
  parent: string | null
  hasChildren: boolean
}

/** Fasteners nest under the part they retain; unconnected fasteners under the part they sit on. */
function buildRows(m: AssemblyManifest, collapsed: Set<string>): Row[] {
  const parentOf = new Map<string, string>()
  for (const conn of m.connections) {
    if (conn.kind === 'screw_retainer') parentOf.set(conn.fastener_id, conn.retained_component_ids[0])
  }
  const overlaps = (a: Component, b: Component) =>
    a.bounds_mm.min[0] < b.bounds_mm.max[0] && a.bounds_mm.max[0] > b.bounds_mm.min[0] && a.bounds_mm.min[1] < b.bounds_mm.max[1] && a.bounds_mm.max[1] > b.bounds_mm.min[1]
  for (const c of m.components) {
    if (c.role !== 'fastener' || parentOf.has(c.id)) continue
    const host = m.components.find((o) => o.role === 'bracket' && overlaps(c, o))
    if (host) parentOf.set(c.id, host.id)
  }
  const top = m.components.filter((c) => !parentOf.has(c.id))
  const rows: Row[] = []
  for (const c of top) {
    const kids = m.components.filter((k) => parentOf.get(k.id) === c.id)
    rows.push({ c, level: 1, parent: null, hasChildren: kids.length > 0 })
    if (!collapsed.has(c.id)) for (const k of kids) rows.push({ c: k, level: 2, parent: c.id, hasChildren: false })
  }
  return rows
}

const ROLE_GLYPH: Record<Component['role'], string> = {
  chassis: 'M2 11h10V5H2zM2 5l2-2h6l2 2',
  cover: 'M1 5h12v2H1z',
  bracket: 'M2 12V5h2v7M10 12V5h2v7M2 4h10',
  service_module: 'M2 2h10v10H2zM7 4.5a2.5 2.5 0 110 5 2.5 2.5 0 010-5',
  electronics: 'M2 4h10v6H2zM4 4V2M7 4V2M10 4V2',
  fastener: 'M4 3h6v2H4zM6 5h2v7H6z',
}

interface Props {
  manifest: AssemblyManifest
  selected: PartId | null
  target: PartId | null
  hidden: PartId[]
  isolated: PartId | null
  dispatch: Dispatch<Action>
}

export const ComponentTree = memo(function ComponentTree({ manifest, selected, target, hidden, isolated, dispatch }: Props) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const rows = useMemo(() => buildRows(manifest, collapsed), [manifest, collapsed])
  const listRef = useRef<HTMLUListElement>(null)
  const focusIndex = Math.max(0, rows.findIndex((r) => r.c.id === selected))

  const focusRow = (i: number) => {
    const r = rows[Math.max(0, Math.min(rows.length - 1, i))]
    if (!r) return
    if (isPartId(r.c.id)) dispatch({ type: 'select', id: r.c.id })
    requestAnimationFrame(() => listRef.current?.querySelector<HTMLElement>(`[data-id="${r.c.id}"]`)?.focus())
  }

  const toggle = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const onKey = (e: KeyboardEvent<HTMLLIElement>, i: number, r: Row) => {
    const id = r.c.id
    if (!isPartId(id)) return
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        focusRow(i + 1)
        break
      case 'ArrowUp':
        e.preventDefault()
        focusRow(i - 1)
        break
      case 'ArrowRight':
        if (r.hasChildren && collapsed.has(id)) toggle(id)
        break
      case 'ArrowLeft':
        if (r.hasChildren && !collapsed.has(id)) toggle(id)
        else if (r.parent) focusRow(rows.findIndex((x) => x.c.id === r.parent))
        break
      case 'Enter':
      case ' ':
        e.preventDefault()
        dispatch({ type: 'select', id })
        break
      case 'h':
      case 'H':
        dispatch({ type: 'toggleHidden', id })
        break
      case 'i':
      case 'I':
        dispatch({ type: 'isolate', id: isolated === id ? null : id })
        break
      case 't':
      case 'T':
        trySetTarget(r.c, dispatch)
        break
    }
  }

  return (
    <nav className="tree" aria-label="Assembly">
      <div className="tree__head">
        <span>Assembly</span>
        <span className="mono">{manifest.components.length} parts</span>
      </div>
      <ul className="tree__list" role="tree" aria-label="Components" ref={listRef}>
        {rows.map((r, i) => {
          const id = r.c.id as PartId
          const isHidden = hidden.includes(id) || (isolated !== null && isolated !== id)
          return (
            <li
              key={id}
              data-id={id}
              role="treeitem"
              aria-level={r.level}
              aria-selected={selected === id}
              aria-expanded={r.hasChildren ? !collapsed.has(id) : undefined}
              tabIndex={i === focusIndex ? 0 : -1}
              className={`tree__row ${selected === id ? 'is-selected' : ''} ${target === id ? 'is-target' : ''} ${isHidden ? 'is-hidden' : ''}`}
              style={{ ['--level' as string]: r.level }}
              onClick={() => dispatch({ type: 'select', id })}
              onDoubleClick={() => dispatch({ type: 'isolate', id: isolated === id ? null : id })}
              onMouseEnter={() => dispatch({ type: 'hover', id })}
              onMouseLeave={() => dispatch({ type: 'hover', id: null })}
              onKeyDown={(e) => onKey(e, i, r)}
            >
              {r.hasChildren ? (
                <button
                  type="button"
                  className="tree__twisty"
                  tabIndex={-1}
                  aria-hidden="true"
                  onClick={(e) => {
                    e.stopPropagation()
                    toggle(id)
                  }}
                >
                  <svg width="10" height="10" viewBox="0 0 10 10" style={{ transform: collapsed.has(id) ? 'rotate(-90deg)' : undefined }}>
                    <path d="M2 3.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.3" />
                  </svg>
                </button>
              ) : (
                <span className="tree__twisty" />
              )}
              <svg className="tree__glyph" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                <path d={ROLE_GLYPH[r.c.role]} fill="none" stroke="currentColor" strokeWidth="1.1" />
              </svg>
              <span className="tree__name">
                {r.c.display_name}
                <span className="mono">{r.c.id}</span>
              </span>
              {target === id && <span className="tree__chip">Target</span>}
              {r.c.fixed && (
                <svg className="tree__lock" width="12" height="12" viewBox="0 0 12 12" aria-label="Fixed" role="img">
                  <title>{r.c.fixed_reason ?? 'Fixed'}</title>
                  <path d="M3 5.5h6v5H3zM4.3 5.5V4a1.7 1.7 0 013.4 0v1.5" fill="none" stroke="currentColor" strokeWidth="1.1" />
                </svg>
              )}
              <button
                type="button"
                className="tree__eye"
                tabIndex={-1}
                aria-label={hidden.includes(id) ? `Show ${r.c.display_name}` : `Hide ${r.c.display_name}`}
                aria-pressed={hidden.includes(id)}
                onClick={(e) => {
                  e.stopPropagation()
                  dispatch({ type: 'toggleHidden', id })
                }}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                  {hidden.includes(id) ? (
                    <path d="M2 7s2-3.5 5-3.5S12 7 12 7s-2 3.5-5 3.5S2 7 2 7zM2.5 2.5l9 9" fill="none" stroke="currentColor" strokeWidth="1.1" />
                  ) : (
                    <>
                      <path d="M2 7s2-3.5 5-3.5S12 7 12 7s-2 3.5-5 3.5S2 7 2 7z" fill="none" stroke="currentColor" strokeWidth="1.1" />
                      <circle cx="7" cy="7" r="1.5" fill="currentColor" />
                    </>
                  )}
                </svg>
              </button>
            </li>
          )
        })}
      </ul>
      <p className="tree__keys">
        <kbd>↑</kbd>
        <kbd>↓</kbd> select <kbd>H</kbd> hide <kbd>I</kbd> isolate <kbd>T</kbd> target
      </p>
    </nav>
  )
})

/** Target selection requires an explicitly replaceable occurrence (FR004). */
export function trySetTarget(c: Component, dispatch: Dispatch<Action>) {
  if (!isPartId(c.id)) return
  if (!c.replaceable) {
    dispatch({
      type: 'notice',
      notice: {
        tone: 'refuse',
        text: c.fixed
          ? `${c.id} cannot be a repair target. ${c.fixed_reason ?? 'It is declared fixed.'}`
          : `${c.id} is not declared replaceable in the manifest, so it cannot be a repair target.`,
      },
    })
    return
  }
  dispatch({ type: 'target', id: c.id })
  dispatch({ type: 'notice', notice: { tone: 'info', text: `${c.id} is the repair target. Results for any earlier target are cleared.` } })
}
