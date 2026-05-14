import { useMemo } from 'react'
import type { ProvincesResponse } from '../api/client'
import type { Scope } from '../scope'

type ProvinceInfo = ProvincesResponse['provinces'][number]

interface SidebarProps {
  provinces: ProvinceInfo[] | null
  scope: Scope
  // null = clear; non-null = scope to that province
  onSelect: (province: string | null) => void
}

export default function Sidebar({ provinces, scope, onSelect }: SidebarProps) {
  // Group by island for orientation — Visayas has nine distinct islands
  // and grouping by island makes the list scannable. When the user has
  // an island scoped, dim the other groups.
  const grouped = useMemo(() => {
    if (!provinces) return [] as Array<[string, ProvinceInfo[]]>
    const by: Record<string, ProvinceInfo[]> = {}
    for (const p of provinces) {
      const k = p.island ?? '—'
      ;(by[k] ??= []).push(p)
    }
    return Object.entries(by).sort(([, a], [, b]) => {
      const sa = a.reduce((s, x) => s + x.total_load_mw, 0)
      const sb = b.reduce((s, x) => s + x.total_load_mw, 0)
      return sb - sa
    })
  }, [provinces])

  const selectedProvince = scope.kind === 'province' ? scope.name : null
  const islandFilter = scope.kind === 'island' ? scope.name : null

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <strong>Provinces</strong>
        <button
          className="sidebar-clear"
          onClick={() => onSelect(null)}
          disabled={scope.kind === 'all'}
          title="Clear selection — show whole grid"
        >
          all
        </button>
      </div>

      {!provinces && <div className="sidebar-loading">Loading…</div>}

      {grouped.map(([island, list]) => {
        const dim = islandFilter != null && islandFilter !== island
        return (
          <div key={island} className={'sidebar-group' + (dim ? ' dim' : '')}>
            <div className="sidebar-island">{island}</div>
            <ul className="sidebar-list">
              {list.sort((a, b) => b.total_load_mw - a.total_load_mw).map((p) => (
                <li key={p.name}>
                  <button
                    className={'sidebar-province' + (selectedProvince === p.name ? ' active' : '')}
                    onClick={() => onSelect(p.name === selectedProvince ? null : p.name)}
                    title={`${p.bus_count} buses (${p.in_service_bus_count} in service) · ${p.total_load_mw.toFixed(0)} MW total load`}
                  >
                    <span className="sidebar-name">{p.name}</span>
                    <span className="sidebar-meta">
                      {p.total_load_mw.toFixed(0)} MW
                      <span className="sidebar-buses">
                        {' · '}{p.in_service_bus_count}/{p.bus_count}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </aside>
  )
}
