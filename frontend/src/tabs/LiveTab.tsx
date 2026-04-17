import { useEffect, useState } from 'react'
import { useEngineStore } from '../store/engineStore'
import { post, del, get } from '../api/rest'
import { send } from '../api/ws'
import StageSVG from '../components/StageSVG'

export default function LiveTab() {
  const { events, fixtureColors, masterDimmer, parkedFixtures, setMasterDimmer } = useEngineStore()
  const [banks, setBanks] = useState<{ name: string; scenes: { name: string }[] }[]>([])

  useEffect(() => {
    get<{ name: string; scenes: { name: string }[] }[]>('/scenes/banks').then(setBanks).catch(() => {})
  }, [])

  const flashEvents  = events.filter(e => e.type === 'flash' || e.name.toUpperCase().includes('BLINDER'))
  const normalEvents = events.filter(e => e.type !== 'flash' && e.type !== 'stop_all' && !e.name.toUpperCase().includes('BLINDER'))
  const stopAll      = events.find(e => e.type === 'stop_all')

  function handleFlash(name: string)   { send({ type: 'flash_event', name }) }
  function handleToggle(name: string)  { post(`/events/${encodeURIComponent(name)}/trigger`).catch(console.error) }
  function handleStopAll()             { post('/events/stop_all').catch(console.error) }
  function handleMaster(v: number)     { setMasterDimmer(v); send({ type: 'set_master', value: v }) }

  function handlePark(idx: number) {
    if (parkedFixtures.includes(idx)) del(`/engine/fixtures/${idx}/park`).catch(console.error)
    else                              post(`/engine/fixtures/${idx}/park`).catch(console.error)
  }

  function handleParkedColor(idx: number, role: string, value: number) {
    send({ type: 'set_parked_color', fixture_idx: idx, role, value })
  }

  const masterPct = Math.round(masterDimmer * 100)

  return (
    <div className="flex h-full gap-3 p-3 overflow-hidden" style={{ background: 'var(--console-bg)' }}>

      {/* ── LEFT: Master + Stage ──────────────────────────── */}
      <div className="flex gap-3 shrink-0">

        {/* Master fader panel */}
        <div className="panel flex flex-col items-center py-3 px-2 gap-2" style={{ minWidth: 56 }}>
          <span className="console-label">MASTER</span>
          <div style={{
            fontSize: 11, fontWeight: 900, letterSpacing: '0.1em',
            color: masterDimmer > 0.5 ? 'var(--accent-amber)' : 'var(--console-label)',
            minHeight: 20,
          }}>{masterPct}%</div>
          <input type="range" min={0} max={1} step={0.01}
            value={masterDimmer}
            onChange={e => handleMaster(parseFloat(e.target.value))}
            className="appearance-none cursor-pointer"
            style={{
              writingMode: 'vertical-lr',
              direction: 'rtl',
              height: 240,
              width: 24,
              accentColor: 'var(--accent-amber)',
            }}
          />
          <button onClick={() => handleMaster(0)}
            style={{
              background: 'linear-gradient(180deg, #300000 0%, #1a0000 100%)',
              border: '1px solid #660000',
              color: 'var(--accent-red)',
              fontFamily: 'inherit',
              fontSize: 9,
              fontWeight: 900,
              letterSpacing: '0.1em',
              padding: '3px 8px',
              borderRadius: 2,
              cursor: 'pointer',
              width: '100%',
            }}>BLK</button>
          <button onClick={() => handleMaster(1)}
            style={{
              background: 'linear-gradient(180deg, #3a2000 0%, #1a1000 100%)',
              border: '1px solid var(--accent-amber)',
              color: 'var(--accent-amber)',
              fontFamily: 'inherit',
              fontSize: 9,
              fontWeight: 900,
              letterSpacing: '0.1em',
              padding: '3px 8px',
              borderRadius: 2,
              cursor: 'pointer',
              width: '100%',
            }}>FULL</button>
        </div>

        {/* Stage */}
        <div className="panel" style={{ width: 580, height: '100%', minHeight: 360 }}>
          <div className="panel-hdr">BÜHNE</div>
          <div style={{ padding: 8, height: 'calc(100% - 29px)' }}>
            <StageSVG fixtures={fixtureColors} width={564} height={320}
              onFixtureClick={handlePark} parkedFixtures={parkedFixtures} />
          </div>
        </div>
      </div>

      {/* ── CENTER: Scenes ────────────────────────────────── */}
      <div className="flex-1 flex flex-col gap-2 overflow-y-auto min-w-0">
        <div className="panel-hdr" style={{ background: 'var(--surface-raised)', borderRadius: 3, border: '1px solid var(--console-border)' }}>SZENEN</div>
        {banks.map(bank => (
          <div key={bank.name} className="panel">
            <div className="panel-hdr">{bank.name}</div>
            <div className="flex flex-wrap gap-1 p-2">
              {bank.scenes.map((scene, idx) => (
                <button key={idx}
                  onClick={() => post(`/scenes/banks/${encodeURIComponent(bank.name)}/scenes/${idx}/load`)}
                  className="exec-btn" style={{ height: 36, minWidth: 80 }}>
                  {scene.name}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* ── RIGHT: Events + Park ─────────────────────────── */}
      <div className="flex flex-col gap-2 overflow-y-auto" style={{ width: 240 }}>

        {/* Blinder */}
        <div className="panel">
          <div className="panel-hdr">BLINDER</div>
          <div className="flex flex-wrap gap-1 p-2">
            {flashEvents.map(ev => (
              <button key={ev.name} onClick={() => handleFlash(ev.name)} className="exec-flash">
                {ev.name.toUpperCase()}
              </button>
            ))}
            {flashEvents.length === 0 && (
              <span className="console-label p-1">Keine Flash-Events</span>
            )}
          </div>
        </div>

        {/* Effekte */}
        <div className="panel">
          <div className="panel-hdr">EFFEKTE</div>
          <div className="grid grid-cols-2 gap-1 p-2">
            {normalEvents.map(ev => (
              <button key={ev.name} onClick={() => handleToggle(ev.name)}
                className={`exec-btn ${ev.active ? 'active' : ''}`}
                style={{ fontSize: 9, height: 38 }}>
                {ev.name}
              </button>
            ))}
            {normalEvents.length === 0 && (
              <span className="console-label p-1 col-span-2">Keine Events</span>
            )}
          </div>
        </div>

        {/* Stop All */}
        {stopAll && (
          <button onClick={handleStopAll} style={{
            background: 'linear-gradient(180deg, #2a0000 0%, #160000 100%)',
            border: '1px solid #660000',
            borderBottom: '1px solid #0a0000',
            color: 'var(--accent-red)',
            fontFamily: 'inherit',
            fontSize: 11,
            fontWeight: 900,
            letterSpacing: '0.2em',
            padding: '10px 0',
            borderRadius: 3,
            cursor: 'pointer',
            width: '100%',
            boxShadow: '0 0 0 0 transparent',
            transition: 'box-shadow 0.1s',
          }}
          onMouseEnter={e => (e.currentTarget.style.boxShadow = '0 0 16px rgba(229,57,53,.3)')}
          onMouseLeave={e => (e.currentTarget.style.boxShadow = '0 0 0 0 transparent')}>
            ■  STOP ALL
          </button>
        )}

        {/* Park */}
        <div className="panel">
          <div className="panel-hdr flex items-center justify-between" style={{ display: 'flex' }}>
            <span>FIXTURE PARK</span>
            <button onClick={() => del('/engine/fixtures/park')}
              className="exec-btn" style={{ height: 18, fontSize: 8, padding: '0 6px' }}>
              ALLE FREI
            </button>
          </div>
          <div className="flex flex-col gap-1 p-2">
            {fixtureColors.map(f => (
              <div key={f.id}>
                <div className="flex items-center gap-1">
                  <span className="flex-1" style={{ fontSize: 10, fontFamily: 'monospace', color: 'var(--console-text)' }}>{f.id}</span>
                  <span style={{ fontSize: 9, color: 'var(--console-label)' }}>A{f.address}</span>
                  <button onClick={() => handlePark(f.idx)}
                    className={`exec-btn ${parkedFixtures.includes(f.idx) ? 'active' : ''}`}
                    style={{ height: 22, minWidth: 44, fontSize: 9 }}>
                    PARK
                  </button>
                </div>
                {parkedFixtures.includes(f.idx) && (
                  <div className="pl-2 pt-1 flex flex-col gap-1">
                    {(['red','green','blue','dimmer'] as const).map(role => (
                      role in f.values && (
                        <div key={role} className="flex items-center gap-2">
                          <span style={{ fontSize: 9, width: 10, color: 'var(--console-label)' }}>{role[0].toUpperCase()}</span>
                          <input type="range" min={0} max={1} step={0.01}
                            defaultValue={f.values[role] ?? 0}
                            onChange={e => handleParkedColor(f.idx, role, parseFloat(e.target.value))}
                            className="flex-1"
                            style={{ accentColor: role === 'red' ? '#ff1744' : role === 'green' ? '#00e676' : role === 'blue' ? '#00b0ff' : 'var(--accent-amber)' }}
                          />
                        </div>
                      )
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
