import { useEffect, useMemo, useState } from 'react'
import { api, type ProvincesResponse } from '../api/client'

type ProvinceInfo = ProvincesResponse['provinces'][number]

interface SidebarProps {
  selected: string | null
  onSelect: (province: string | null) => void
}

export default function Sidebar({ selected, onSelect }: SidebarProps) {
  const [provinces, setProvinces] = useState<ProvinceInfo[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.provinces()
      .then((d) => { if (!cancelled) setProvinces(d.provinces) })
      .catch((e) => { if (!cancelled) setError(String(e)) })
    return () => { cancelled = true }
  }, [])

  // Group by island for orientation — Visayas has ~five distinct islands
  // and grouping by island makes the list scannable at a glance.
  const grouped = useMemo(() => {
    if (!provinces) return [] as Array<[string, ProvinceInfo[]]>
    const by: Record<string, ProvinceInfo[]> = {}
    for (const p of provinces) {
      const k = p.island ?? '—'
      ;(by[k] ??= []).push(p)
    }
    // Sort island groups by total load (descending) so the biggest
    // electrical centres surface first.
    return Object.entries(by).sort(([, a], [, b]) => {
      const sa = a.reduce((s, x) => s + x.total_load_mw, 0)
      const sb = b.reduce((s, x) => s + x.total_load_mw, 0)
      return sb - sa
    })
  }, [provinces])

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <strong>Provinces</strong>
        <button
          className="sidebar-clear"
          onClick={() => onSelect(null)}
          disabled={selected === null}
          title="Clear selection — show whole grid"
        >
          all
        </button>
      </div>

      {error && <div className="sidebar-error">{error}</div>}
      {!provinces && !error && <div className="sidebar-loading">Loading…</div>}

      {grouped.map(([island, list]) => (
        <div key={island} className="sidebar-group">
          <div className="sidebar-island">{island}</div>
          <ul className="sidebar-list">
            {list.sort((a, b) => b.total_load_mw - a.total_load_mw).map((p) => (
              <li key={p.name}>
                <button
                  className={'sidebar-province' + (selected === p.name ? ' active' : '')}
                  onClick={() => onSelect(p.name === selected ? null : p.name)}
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
      ))}
    </aside>
  )
}
