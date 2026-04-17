import { useEffect, useRef, useState } from 'react'
import { get, post, del } from '../api/rest'
import { useEngineStore } from '../store/engineStore'

interface SnapPoint { idx: number; x: number; y: number; occupied: boolean; fixture_id: string | null }
interface TraverseData { name: string; x1: number; y1: number; x2: number; y2: number; snap_points: SnapPoint[] }

const STAGE_W = 1200
const STAGE_H = 800
const SNAP_RADIUS = 30

export default function TraverseTab() {
  const { fixtureColors } = useEngineStore()
  const [traverses, setTraverses]     = useState<TraverseData[]>([])
  const [profiles, setProfiles]       = useState<string[]>([])
  const [selectedProfile, setSelectedProfile] = useState('')
  const [hoveredSnap, setHoveredSnap] = useState<{ traverseName: string; idx: number } | null>(null)
  const [ghostPos, setGhostPos]       = useState<{ x: number; y: number } | null>(null)
  const [placing, setPlacing]         = useState(false)
  const svgRef = useRef<SVGSVGElement>(null)

  function reload() {
    get<TraverseData[]>('/traverses').then(setTraverses).catch(() => {})
  }

  useEffect(() => {
    reload()
    get<string[]>('/fixtures/profiles').then(p => {
      setProfiles(p)
      if (p.length) setSelectedProfile(p[0])
    }).catch(() => {})
  }, [])

  function svgCoords(e: React.MouseEvent<SVGSVGElement>): { x: number; y: number } {
    const rect = svgRef.current!.getBoundingClientRect()
    return {
      x: (e.clientX - rect.left) / rect.width  * STAGE_W,
      y: (e.clientY - rect.top)  / rect.height * STAGE_H,
    }
  }

  function findNearestSnap(x: number, y: number) {
    let best: { traverseName: string; idx: number; sp: SnapPoint; dist: number } | null = null
    for (const t of traverses) {
      for (const sp of t.snap_points) {
        const dist = Math.hypot(sp.x - x, sp.y - y)
        if (dist < SNAP_RADIUS && (!best || dist < best.dist))
          best = { traverseName: t.name, idx: sp.idx, sp, dist }
      }
    }
    return best ? { traverseName: best.traverseName, idx: best.idx, sp: best.sp } : null
  }

  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    if (!placing) return
    const { x, y } = svgCoords(e)
    setGhostPos({ x, y })
    const snap = findNearestSnap(x, y)
    setHoveredSnap(snap ? { traverseName: snap.traverseName, idx: snap.idx } : null)
  }

  async function handleClick(e: React.MouseEvent<SVGSVGElement>) {
    if (!placing || !selectedProfile) return
    const { x, y } = svgCoords(e)
    const snap = findNearestSnap(x, y)
    if (!snap || snap.sp.occupied) return
    await post('/fixtures/place', { profile_id: selectedProfile, traverse_name: snap.traverseName, snap_index: snap.idx })
    reload()
  }

  async function handleFixtureClick(fixtureId: string) {
    if (window.confirm(`Fixture "${fixtureId}" löschen?`)) {
      await del(`/fixtures/${encodeURIComponent(fixtureId)}`)
      reload()
    }
  }

  async function addTraverse() {
    const name = prompt('Traverse Name:', `Traverse ${traverses.length + 1}`)
    if (!name) return
    await post('/traverses', { name, x1: 100, y1: 200, x2: 1100, y2: 200, snap_distance: 40 })
    reload()
  }

  async function deleteTraverse(name: string) {
    if (window.confirm(`Traverse "${name}" und alle Fixtures löschen?`)) {
      await del(`/traverses/${encodeURIComponent(name)}`)
      reload()
    }
  }

  return (
    <div className="flex h-full gap-3 p-3 overflow-hidden" style={{ background: 'var(--console-bg)' }}>

      {/* ── Stage SVG ────────────────────────────────────── */}
      <div className="panel flex-1 flex flex-col overflow-hidden">
        <div className="panel-hdr flex items-center gap-3" style={{ display: 'flex' }}>
          <span>BÜHNEN-EDITOR</span>
          <button onClick={() => setPlacing(!placing)}
            className={`exec-btn ${placing ? 'active' : ''}`}
            style={{ height: 20, fontSize: 8, padding: '0 8px' }}>
            {placing ? '● PLATZIEREN' : '○ PLATZIEREN'}
          </button>
          {placing && (
            <select value={selectedProfile} onChange={e => setSelectedProfile(e.target.value)}
              style={{ fontSize: 9 }}>
              {profiles.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          )}
        </div>

        <svg
          ref={svgRef}
          viewBox={`0 0 ${STAGE_W} ${STAGE_H}`}
          style={{
            flex: 1,
            background: '#06060a',
            cursor: placing ? 'crosshair' : 'default',
          }}
          onMouseMove={handleMouseMove}
          onClick={handleClick}
          onMouseLeave={() => { setGhostPos(null); setHoveredSnap(null) }}
        >
          {/* Traverses */}
          {traverses.map(t => (
            <g key={t.name}>
              <line x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2}
                stroke="#2a2a3a" strokeWidth={8} strokeLinecap="round" />
              <line x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2}
                stroke="#3a3a50" strokeWidth={2} strokeLinecap="round" />
              <text x={(t.x1 + t.x2) / 2} y={Math.min(t.y1, t.y2) - 14}
                textAnchor="middle" fontSize={12} fill="#40405a" fontFamily="monospace" fontWeight="bold">
                {t.name.toUpperCase()}
              </text>
              {t.snap_points.map(sp => {
                const isHovered = hoveredSnap?.traverseName === t.name && hoveredSnap?.idx === sp.idx
                return (
                  <circle key={sp.idx} cx={sp.x} cy={sp.y}
                    r={isHovered ? 9 : 5}
                    fill={sp.occupied ? '#1e1e30' : isHovered ? 'rgba(0,200,224,0.15)' : '#0a0a14'}
                    stroke={isHovered ? 'var(--accent-cyan)' : '#2a2a42'}
                    strokeWidth={isHovered ? 2 : 1}
                    style={{ transition: 'r 0.1s' }}
                  />
                )
              })}
            </g>
          ))}

          {/* Fixtures */}
          {fixtureColors.map(f => (
            <g key={f.id} onClick={(e) => { e.stopPropagation(); handleFixtureClick(f.id) }}
               style={{ cursor: 'pointer' }}>
              {(f.r + f.g + f.b) > 10 && (
                <circle cx={f.x} cy={f.y} r={26}
                  fill={`rgba(${f.r},${f.g},${f.b},0.1)`} />
              )}
              <circle cx={f.x} cy={f.y} r={15}
                fill={`rgb(${f.r},${f.g},${f.b})`}
                stroke="#404058" strokeWidth={2} />
              <text x={f.x} y={f.y + 30} textAnchor="middle"
                fontSize={11} fill="#505070" fontFamily="monospace">
                {f.id}
              </text>
            </g>
          ))}

          {/* Ghost cursor */}
          {placing && ghostPos && (
            <circle cx={ghostPos.x} cy={ghostPos.y} r={15}
              fill="rgba(0,200,224,0.12)"
              stroke="var(--accent-cyan)" strokeWidth={1.5} strokeDasharray="5 4" />
          )}
        </svg>
      </div>

      {/* ── Sidebar ──────────────────────────────────────── */}
      <div className="panel flex flex-col overflow-hidden" style={{ width: 200 }}>
        <div className="panel-hdr">TRAVERSES</div>
        <div className="flex flex-col gap-1 p-2 flex-1 overflow-y-auto">
          {traverses.map(t => (
            <div key={t.name} className="flex items-center justify-between"
                 style={{ background: 'var(--surface-raised)', border: '1px solid var(--console-border)', borderRadius: 2, padding: '4px 8px' }}>
              <span style={{ fontSize: 10, color: 'var(--console-text)', letterSpacing: '0.05em' }}>{t.name}</span>
              <button onClick={() => deleteTraverse(t.name)}
                style={{ background: 'none', border: 'none', color: 'var(--accent-red)', cursor: 'pointer', fontSize: 9 }}>
                DEL
              </button>
            </div>
          ))}
        </div>
        <div className="p-2 flex flex-col gap-2" style={{ borderTop: '1px solid var(--console-border)' }}>
          <button onClick={addTraverse} className="exec-btn w-full" style={{ height: 34 }}>
            + TRAVERSE
          </button>
          <button onClick={() => post('/project/save')} className="exec-btn active-cyan w-full" style={{ height: 34 }}>
            SPEICHERN
          </button>
        </div>
      </div>
    </div>
  )
}
