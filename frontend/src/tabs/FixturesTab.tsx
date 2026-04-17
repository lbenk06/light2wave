import { useEffect, useState } from 'react'
import { get, post } from '../api/rest'

interface FixtureInfo {
  idx:        number
  id:         string
  profile_id: string
  address:    number
  channels:   string[]
  values:     Record<string, number>
}

const ROLES = ['dimmer', 'red', 'green', 'blue', 'white', 'strobe', 'pan', 'tilt', 'speed', 'unused']

const ROLE_COLOR: Record<string, string> = {
  red:     '#e53935',
  green:   '#43a047',
  blue:    '#00b0ff',
  white:   '#ccc',
  dimmer:  'var(--accent-amber)',
  strobe:  '#ab47bc',
  pan:     '#00c8e0',
  tilt:    '#00c8e0',
  speed:   '#808080',
}

export default function FixturesTab() {
  const [fixtures, setFixtures] = useState<FixtureInfo[]>([])
  const [localVals, setLocalVals] = useState<Record<string, number>>({})

  // Profile editor state
  const [profileName, setProfileName]   = useState('')
  const [editorChannels, setEditorChannels] = useState<{ role: string }[]>([{ role: 'dimmer' }])
  const [editorOpen, setEditorOpen]     = useState(false)
  const [saveMsg, setSaveMsg]           = useState('')

  function reload() {
    get<FixtureInfo[]>('/fixtures').then(list => {
      setFixtures(list)
      // Seed local values
      const init: Record<string, number> = {}
      list.forEach(f => {
        f.channels.forEach(role => {
          if (role !== 'unused') init[`${f.idx}_${role}`] = f.values[role] ?? 0
        })
      })
      setLocalVals(init)
    }).catch(() => {})
  }

  useEffect(() => { reload() }, [])

  function handleSlider(idx: number, role: string, raw: number) {
    const value = raw / 255
    const key = `${idx}_${role}`
    setLocalVals(prev => ({ ...prev, [key]: value }))
    post(`/fixtures/${idx}/channel`, { role, value }).catch(() => {})
  }

  // ── Profile editor ────────────────────────────────────────
  function addChannel()  { setEditorChannels(c => [...c, { role: 'unused' }]) }
  function removeChannel(i: number) { setEditorChannels(c => c.filter((_, j) => j !== i)) }
  function setChannelRole(i: number, role: string) {
    setEditorChannels(c => c.map((ch, j) => j === i ? { role } : ch))
  }

  async function saveProfile() {
    if (!profileName.trim()) { setSaveMsg('Name fehlt!'); return }
    if (editorChannels.length === 0) { setSaveMsg('Min. 1 Kanal!'); return }
    try {
      await post('/fixtures/profiles', { name: profileName.trim(), channels: editorChannels })
      setSaveMsg(`Profil "${profileName}" gespeichert.`)
      setProfileName('')
      setEditorChannels([{ role: 'dimmer' }])
      reload()
    } catch (e: any) {
      setSaveMsg(e.message ?? 'Fehler')
    }
  }

  return (
    <div className="flex flex-col h-full p-3 gap-4 overflow-y-auto" style={{ background: 'var(--console-bg)' }}>

      {/* ── Header ──────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <span style={{ fontSize: 13, fontWeight: 900, letterSpacing: '0.25em', color: 'var(--console-text)' }}>
          GERÄTE STEUERUNG
        </span>
        <button onClick={reload} className="exec-btn" style={{ height: 30, fontSize: 9 }}>
          ↻ REFRESH
        </button>
      </div>

      {/* ── Fixture cards ───────────────────────────────── */}
      {fixtures.length === 0 ? (
        <div className="panel p-4">
          <span className="console-label">Keine Geräte vorhanden — gehe zum TRAVERSE Tab um Fixtures zu platzieren.</span>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 8 }}>
          {fixtures.map(f => (
            <div key={f.idx} className="panel">
              <div className="panel-hdr flex items-center justify-between" style={{ display: 'flex' }}>
                <span>{f.id}</span>
                <span style={{ color: 'var(--console-label)', fontSize: 8, letterSpacing: '0.1em' }}>
                  ADR {f.address}  ·  {f.profile_id}
                </span>
              </div>
              <div className="flex flex-col gap-2 p-3">
                {f.channels.map((role, chIdx) => {
                  if (role === 'unused') return null
                  const key   = `${f.idx}_${role}`
                  const val01 = localVals[key] ?? f.values[role] ?? 0
                  const val255 = Math.round(val01 * 255)
                  const color = ROLE_COLOR[role] ?? 'var(--console-label)'
                  return (
                    <div key={chIdx} className="flex items-center gap-2">
                      <span style={{ fontSize: 9, fontWeight: 900, width: 40, color, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                        {role}
                      </span>
                      <input type="range" min={0} max={255} step={1}
                        value={val255}
                        onChange={e => handleSlider(f.idx, role, parseInt(e.target.value))}
                        className="flex-1"
                        style={{ accentColor: color }}
                      />
                      <span style={{ fontSize: 9, fontFamily: 'monospace', width: 28, textAlign: 'right', color: 'var(--console-label)' }}>
                        {val255}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Profile editor (collapsible) ────────────────── */}
      <div className="panel">
        <button
          onClick={() => setEditorOpen(o => !o)}
          className="panel-hdr w-full text-left flex items-center justify-between"
          style={{ cursor: 'pointer', display: 'flex', background: 'none', border: 'none', color: 'var(--console-label)', fontFamily: 'inherit' }}>
          <span>NEUES GERÄTEPROFIL ERSTELLEN</span>
          <span style={{ fontSize: 11 }}>{editorOpen ? '▲' : '▼'}</span>
        </button>

        {editorOpen && (
          <div className="flex flex-col gap-4 p-3" style={{ maxWidth: 480 }}>

            {/* Name */}
            <div className="flex flex-col gap-1">
              <span className="console-label">PROFILNAME</span>
              <input
                value={profileName}
                onChange={e => setProfileName(e.target.value)}
                placeholder="z.B. Mein LED Bar"
                style={{
                  background: 'var(--surface-raised)',
                  border: '1px solid var(--console-border)',
                  color: 'var(--console-text)',
                  fontFamily: 'inherit',
                  fontSize: 11,
                  padding: '6px 10px',
                  borderRadius: 2,
                  outline: 'none',
                  width: '100%',
                }}
              />
            </div>

            {/* Channel list */}
            <div className="flex flex-col gap-1">
              <span className="console-label">KANALBELEGUNG</span>
              {editorChannels.map((ch, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span style={{ fontSize: 9, color: 'var(--accent-cyan)', fontWeight: 900, width: 36, fontFamily: 'monospace' }}>
                    CH {String(i + 1).padStart(2, '0')}
                  </span>
                  <select value={ch.role} onChange={e => setChannelRole(i, e.target.value)} style={{ flex: 1 }}>
                    {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                  <button onClick={() => removeChannel(i)}
                    style={{ background: 'none', border: 'none', color: 'var(--accent-red)', cursor: 'pointer', fontSize: 13, padding: '0 4px' }}>
                    ✕
                  </button>
                </div>
              ))}
              <button onClick={addChannel} className="exec-btn" style={{ height: 28, fontSize: 9, marginTop: 4, width: 120 }}>
                + KANAL
              </button>
            </div>

            {/* Save */}
            <div className="flex items-center gap-3">
              <button onClick={saveProfile} className="exec-btn active" style={{ height: 34, minWidth: 120 }}>
                SPEICHERN
              </button>
              {saveMsg && (
                <span style={{ fontSize: 10, color: saveMsg.includes('!') || saveMsg.includes('Fehler') ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                  {saveMsg}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
