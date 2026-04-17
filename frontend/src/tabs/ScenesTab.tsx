import { useEffect, useState } from 'react'
import { get, post, del } from '../api/rest'

interface Scene { name: string; color: string }
interface Bank  { name: string; scenes: Scene[] }

export default function ScenesTab() {
  const [banks, setBanks]       = useState<Bank[]>([])
  const [activeBank, setActiveBank] = useState<string | null>(null)

  function reload() {
    get<Bank[]>('/scenes/banks').then(b => {
      setBanks(b)
      if (!activeBank && b.length) setActiveBank(b[0].name)
    }).catch(() => {})
  }

  useEffect(() => { reload() }, [])

  const bank = banks.find(b => b.name === activeBank)

  async function addBank() {
    const name = prompt('Bank Name:')
    if (!name) return
    await post('/scenes/banks', { name })
    reload(); setActiveBank(name)
  }

  async function deleteBank(name: string) {
    if (!window.confirm(`Bank "${name}" löschen?`)) return
    await del(`/scenes/banks/${encodeURIComponent(name)}`)
    reload()
  }

  async function captureScene() {
    if (!activeBank) return
    const name = prompt('Szenen Name:')
    if (!name) return
    await post(`/scenes/banks/${encodeURIComponent(activeBank)}/scenes/capture`, { name })
    reload()
  }

  async function loadScene(bankName: string, idx: number) {
    await post(`/scenes/banks/${encodeURIComponent(bankName)}/scenes/${idx}/load`)
  }

  async function deleteScene(bankName: string, idx: number) {
    await del(`/scenes/banks/${encodeURIComponent(bankName)}/scenes/${idx}`)
    reload()
  }

  return (
    <div className="flex h-full gap-3 p-3 overflow-hidden" style={{ background: 'var(--console-bg)' }}>

      {/* ── Bank sidebar ─────────────────────────────────── */}
      <div className="panel flex flex-col overflow-hidden" style={{ width: 180 }}>
        <div className="panel-hdr flex items-center justify-between" style={{ display: 'flex' }}>
          <span>BANKS</span>
          <button onClick={addBank} className="exec-btn" style={{ height: 18, fontSize: 8, padding: '0 6px' }}>
            + NEU
          </button>
        </div>
        <div className="flex flex-col gap-1 p-2 overflow-y-auto flex-1">
          {banks.map(b => (
            <div key={b.name} className="flex items-center gap-1">
              <button onClick={() => setActiveBank(b.name)}
                className={`exec-btn flex-1 text-left ${activeBank === b.name ? 'active' : ''}`}
                style={{ height: 32, fontSize: 10 }}>
                {b.name}
              </button>
              <button onClick={() => deleteBank(b.name)}
                style={{ background: 'none', border: 'none', color: 'var(--accent-red)', cursor: 'pointer', fontSize: 11, padding: '0 4px' }}>
                ✕
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* ── Scene grid ───────────────────────────────────── */}
      <div className="flex-1 flex flex-col gap-3 overflow-hidden">
        {bank ? (
          <>
            <div className="flex items-center justify-between">
              <span style={{ fontSize: 14, fontWeight: 900, letterSpacing: '0.2em', color: 'var(--accent-amber)' }}>
                {bank.name}
              </span>
              <div className="flex gap-2">
                <button onClick={captureScene} className="exec-btn active" style={{ height: 34 }}>
                  + SZENE AUFNEHMEN
                </button>
                <button onClick={() => post('/project/save')} className="exec-btn active-cyan" style={{ height: 34 }}>
                  SPEICHERN
                </button>
              </div>
            </div>

            <div className="flex flex-wrap gap-2 overflow-y-auto">
              {bank.scenes.map((scene, idx) => (
                <div key={idx} className="relative group">
                  <button onClick={() => loadScene(bank.name, idx)}
                    className="exec-btn" style={{ minWidth: 110, height: 48, fontSize: 10 }}>
                    {scene.name}
                  </button>
                  <button onClick={() => deleteScene(bank.name, idx)}
                    className="absolute -top-1 -right-1 hidden group-hover:flex items-center justify-center"
                    style={{
                      width: 16, height: 16, borderRadius: '50%',
                      background: 'var(--accent-red)', color: '#fff',
                      border: 'none', cursor: 'pointer', fontSize: 8,
                    }}>✕</button>
                </div>
              ))}
              {bank.scenes.length === 0 && (
                <span className="console-label" style={{ marginTop: 8 }}>
                  Keine Szenen — "Szene aufnehmen" um aktuelle Lichter zu speichern.
                </span>
              )}
            </div>
          </>
        ) : (
          <span className="console-label" style={{ marginTop: 8 }}>Keine Bank ausgewählt.</span>
        )}
      </div>
    </div>
  )
}
