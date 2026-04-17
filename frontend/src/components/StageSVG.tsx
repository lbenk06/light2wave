import { useEffect, useState } from 'react'
import { get } from '../api/rest'
import type { FixtureColor } from '../store/engineStore'

interface SnapPoint { idx: number; x: number; y: number; occupied: boolean; fixture_id: string | null }
interface TraverseData { name: string; x1: number; y1: number; x2: number; y2: number; snap_points: SnapPoint[] }

interface Props {
  fixtures: FixtureColor[]
  width: number
  height: number
  parkedFixtures?: number[]
  onFixtureClick?: (idx: number) => void
}

const STAGE_W = 1200
const STAGE_H = 800

export default function StageSVG({ fixtures, width, height, parkedFixtures = [], onFixtureClick }: Props) {
  const [traverses, setTraverses] = useState<TraverseData[]>([])

  useEffect(() => {
    get<TraverseData[]>('/traverses').then(setTraverses).catch(() => {})
  }, [])

  return (
    <svg
      width={width}
      height={height}
      style={{ background: '#050508', border: '1px solid var(--console-border)', borderRadius: 2 }}
      viewBox={`0 0 ${STAGE_W} ${STAGE_H}`}
    >
      {/* Traverses */}
      {traverses.map(t => (
        <g key={t.name}>
          <line x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2}
            stroke="#1e1e2e" strokeWidth={4} strokeLinecap="round" />
          {t.snap_points.map(sp => (
            <circle key={sp.idx} cx={sp.x} cy={sp.y} r={4}
              fill={sp.occupied ? '#2a2a4a' : '#1a1a2a'}
              stroke="#2a2a3a" strokeWidth={1} />
          ))}
        </g>
      ))}

      {/* Fixtures */}
      {fixtures.map(f => {
        const isParked = parkedFixtures.includes(f.idx)
        const glow = (f.r + f.g + f.b) > 10
        return (
          <g key={f.id} onClick={() => onFixtureClick?.(f.idx)} style={{ cursor: 'pointer' }}>
            {glow && (
              <circle cx={f.x} cy={f.y} r={20}
                fill={`rgba(${f.r},${f.g},${f.b},0.15)`} />
            )}
            <circle cx={f.x} cy={f.y} r={12}
              fill={`rgb(${f.r},${f.g},${f.b})`}
              stroke={isParked ? '#ffd600' : '#2a2a3a'}
              strokeWidth={isParked ? 2 : 1}
            />
            <text x={f.x} y={f.y + 24} textAnchor="middle"
              fontSize={9} fill="#4a4a6a" fontFamily="monospace">
              {f.id}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
