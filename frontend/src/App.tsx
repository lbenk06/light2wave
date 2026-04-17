import { useState } from 'react'
import LiveTab from './tabs/LiveTab'
import AudioTab from './tabs/AudioTab'
import TraverseTab from './tabs/TraverseTab'
import ScenesTab from './tabs/ScenesTab'
import DmxTab from './tabs/DmxTab'
import FixturesTab from './tabs/FixturesTab'

// Init stores (wire WS handlers on import)
import './store/engineStore'
import './store/audioStore'

const TABS = ['LIVE', 'AUDIO', 'GERÄTE', 'TRAVERSE', 'SZENEN', 'DMX'] as const
type Tab = typeof TABS[number]

export default function App() {
  const [tab, setTab] = useState<Tab>('LIVE')

  return (
    <div className="flex flex-col h-screen" style={{ background: 'var(--console-bg)' }}>

      {/* ── Top bar ─────────────────────────────────────────── */}
      <div className="flex items-stretch shrink-0" style={{
        background: 'linear-gradient(180deg, #181820 0%, #0f0f16 100%)',
        borderBottom: '2px solid var(--console-border)',
        minHeight: 44,
      }}>
        {/* Brand */}
        <div className="flex items-center px-5 gap-3"
             style={{ borderRight: '1px solid var(--console-border)' }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: 'var(--accent-amber)',
            boxShadow: '0 0 8px var(--accent-amber)',
          }} />
          <span style={{
            fontFamily: 'inherit',
            fontSize: 13,
            fontWeight: 900,
            letterSpacing: '0.35em',
            color: 'var(--accent-amber)',
          }}>LIGHT2WAVE</span>
        </div>

        {/* Tabs — styled like console function keys */}
        <nav className="flex">
          {TABS.map((t, i) => {
            const isActive = tab === t
            return (
              <button key={t} onClick={() => setTab(t)}
                style={{
                  background: isActive
                    ? 'linear-gradient(180deg, #2a1e00 0%, #1a1400 100%)'
                    : 'transparent',
                  borderRight: '1px solid var(--console-border)',
                  borderBottom: isActive
                    ? '2px solid var(--accent-amber)'
                    : '2px solid transparent',
                  color: isActive ? 'var(--accent-amber)' : 'var(--console-label)',
                  fontFamily: 'inherit',
                  fontSize: 10,
                  fontWeight: 900,
                  letterSpacing: '0.18em',
                  padding: '0 20px',
                  cursor: 'pointer',
                  transition: 'all 0.1s',
                  minWidth: 80,
                  boxShadow: isActive ? 'inset 0 0 16px rgba(255,145,0,.08)' : 'none',
                }}>
                <span style={{ display: 'block', fontSize: 8, color: 'var(--console-label)', marginBottom: 1 }}>
                  F{i + 1}
                </span>
                {t}
              </button>
            )
          })}
        </nav>

        {/* Right: version */}
        <div className="flex items-center ml-auto px-4" style={{ borderLeft: '1px solid var(--console-border)' }}>
          <span style={{ fontSize: 9, letterSpacing: '0.12em', color: 'var(--console-label)' }}>v2.0</span>
        </div>
      </div>

      {/* ── Tab content ─────────────────────────────────────── */}
      <div className="flex-1 overflow-hidden">
        {tab === 'LIVE'     && <LiveTab />}
        {tab === 'AUDIO'    && <AudioTab />}
        {tab === 'GERÄTE'   && <FixturesTab />}
        {tab === 'TRAVERSE' && <TraverseTab />}
        {tab === 'SZENEN'   && <ScenesTab />}
        {tab === 'DMX'      && <DmxTab />}
      </div>
    </div>
  )
}
