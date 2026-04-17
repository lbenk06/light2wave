import { useRef, useState, useEffect } from 'react'
import { useAudioStore } from '../store/audioStore'
import { post, get, upload } from '../api/rest'
import { send } from '../api/ws'

export default function AudioTab() {
  const { live, file, playSettings, magicAuto } = useAudioStore()
  const [devices, setDevices] = useState<Record<string, string>>({})
  const [selectedDevice, setSelectedDevice] = useState<number | null>(null)
  const [banks, setBanks] = useState<{ name: string }[]>([])
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    get<Record<string, string>>('/audio/devices').then(d => {
      setDevices(d)
      const first = parseInt(Object.keys(d)[0] ?? '0')
      if (!isNaN(first)) setSelectedDevice(first)
    }).catch(() => {})
    get<{ name: string }[]>('/scenes/banks').then(setBanks).catch(() => {})
    get('/audio/play_settings').then((ps: any) => {
      useAudioStore.getState().setPlaySettings(ps)
    }).catch(() => {})
  }, [])

  const phase = playSettings.source_mode === 'MP3' ? file.last_state : live.phase
  const phaseClass = phase === 'DROP' ? 'phase-drop' : phase === 'BUILDUP' ? 'phase-buildup' : phase === 'BREAK' ? 'phase-break' : 'phase-wait'

  async function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    await upload('/audio/file/upload', f)
  }

  function toggleAudioMode() {
    post('/audio/play_settings', { is_active: !playSettings.is_active })
  }

  function togglePlay()  { post('/audio/file/play') }

  function toggleLive() {
    if (live.is_listening) post('/audio/live/stop')
    else if (selectedDevice !== null) post('/audio/live/start', { device_id: selectedDevice })
  }

  function setMode(mode: string)             { post('/audio/play_settings', { mode }) }
  function setSourceMode(source_mode: string) { post('/audio/play_settings', { source_mode }) }
  function setMagicAuto(key: string, value: unknown) { send({ type: 'set_magic_auto', key, value }) }

  return (
    <div className="flex flex-col h-full p-3 gap-3 overflow-y-auto" style={{ background: 'var(--console-bg)' }}>

      {/* ── Header row ──────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <span style={{ fontSize: 13, fontWeight: 900, letterSpacing: '0.25em', color: 'var(--console-text)' }}>SOUND TO LIGHT</span>
        <button onClick={toggleAudioMode}
          className={`exec-btn ${playSettings.is_active ? 'active' : ''}`}
          style={{ height: 32, minWidth: 160 }}>
          AUDIO MODE: {playSettings.is_active ? 'AN' : 'AUS'}
        </button>
      </div>

      {/* ── Source mode selector ────────────────────────── */}
      <div className="flex gap-1" style={{ height: 36 }}>
        {['MP3', 'LIVE'].map(m => (
          <button key={m} onClick={() => setSourceMode(m)}
            className={`exec-btn flex-1 ${playSettings.source_mode === m ? 'active' : ''}`}>
            {m}
          </button>
        ))}
      </div>

      <div className="flex gap-3">

        {/* ── Input panel ─────────────────────────────── */}
        <div className="panel flex-1">
          {playSettings.source_mode === 'MP3' ? (
            <>
              <div className="panel-hdr">PRE-ANALYSIS MP3</div>
              <div className="flex flex-col gap-3 p-3">
                <input ref={fileRef} type="file" accept=".mp3,.wav,.ogg,.flac" onChange={handleFileSelect} className="hidden" />
                <button onClick={() => fileRef.current?.click()}
                  className="exec-btn active-cyan w-full" style={{ height: 38 }}>
                  DATEI AUSWÄHLEN
                </button>
                {file.file_path && (
                  <div style={{ fontSize: 10, color: 'var(--console-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {file.file_path.split(/[/\\]/).pop()}
                  </div>
                )}
                {file.bpm > 0 && (
                  <div style={{ fontSize: 16, fontWeight: 900, color: 'var(--accent-purple)', letterSpacing: '0.1em' }}>
                    BPM  {file.bpm.toFixed(1)}
                  </div>
                )}
                <button onClick={togglePlay}
                  className="exec-btn w-full" style={{
                    height: 40,
                    ...(file.is_playing
                      ? { background: 'linear-gradient(180deg,#300000,#1a0000)', borderColor: 'var(--accent-red)', color: 'var(--accent-red)' }
                      : { background: 'linear-gradient(180deg,#003000,#001a00)', borderColor: 'var(--accent-green)', color: 'var(--accent-green)' }),
                  }}>
                  {file.is_playing ? '■  STOP MP3' : '▶  PLAY MP3'}
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="panel-hdr">LIVE INPUT</div>
              <div className="flex flex-col gap-3 p-3">
                <select value={selectedDevice ?? ''} onChange={e => setSelectedDevice(parseInt(e.target.value))}
                  className="w-full">
                  {Object.entries(devices).map(([id, name]) => (
                    <option key={id} value={id}>{name}</option>
                  ))}
                </select>

                <div>
                  <div className="console-label mb-1">PEGEL</div>
                  <div className="vu-bar">
                    <div style={{
                      height: '100%', transition: 'width 0.05s',
                      width: `${live.volume * 100}%`,
                      background: 'linear-gradient(90deg, var(--accent-green), var(--accent-amber))',
                    }} />
                  </div>
                </div>

                <div>
                  <div className="console-label mb-1">BEAT LEVEL</div>
                  <div className="vu-bar">
                    <div style={{
                      height: '100%', transition: 'width 0.05s',
                      width: `${live.level * 100}%`,
                      background: live.level > 0.8 ? 'var(--accent-red)' : 'var(--accent-cyan)',
                    }} />
                  </div>
                </div>

                {live.ml_active && (
                  <div style={{ fontSize: 9, fontWeight: 900, letterSpacing: '0.15em', color: 'var(--accent-cyan)' }}>
                    ● ML-MODELL AKTIV
                  </div>
                )}

                <button onClick={toggleLive}
                  className="exec-btn w-full" style={{
                    height: 40,
                    ...(live.is_listening
                      ? { background: 'linear-gradient(180deg,#300000,#1a0000)', borderColor: 'var(--accent-red)', color: 'var(--accent-red)' }
                      : { background: 'linear-gradient(180deg,#003000,#001a00)', borderColor: 'var(--accent-green)', color: 'var(--accent-green)' }),
                  }}>
                  {live.is_listening ? '■  TRENNEN' : '▶  VERBINDEN'}
                </button>
              </div>
            </>
          )}
        </div>

        {/* ── Show control panel ──────────────────────── */}
        <div className="panel flex-1 flex flex-col">
          <div className="panel-hdr">SHOW CONTROL</div>
          <div className="flex flex-col gap-4 p-3 flex-1">

            {/* Phase + Beat display */}
            <div className="flex gap-3">
              <div>
                <div className="console-label mb-1">PHASE</div>
                <div className={`lcd ${phaseClass}`}>{phase || 'WAIT'}</div>
              </div>
              <div>
                <div className="console-label mb-1">BEAT</div>
                <div className="lcd">
                  {playSettings.source_mode === 'LIVE' ? `${live.beat_index + 1} / 4` : '--'}
                </div>
              </div>
            </div>

            {/* Mode selector */}
            <div>
              <div className="console-label mb-2">MODUS</div>
              <div className="flex gap-1 flex-wrap">
                {['Scene Sync', 'Custom Timeline', 'Magic Auto'].map(m => (
                  <button key={m} onClick={() => setMode(m)}
                    className={`exec-btn ${playSettings.mode === m ? 'active' : ''}`}
                    style={{ height: 32, fontSize: 9 }}>
                    {m}
                  </button>
                ))}
              </div>
            </div>

            {/* Scene Sync bank */}
            {playSettings.mode === 'Scene Sync' && (
              <div>
                <div className="console-label mb-1">BANK</div>
                <select className="w-full"
                  value={playSettings.selected_bank ?? ''}
                  onChange={e => post('/audio/play_settings', { selected_bank: e.target.value })}>
                  {banks.map(b => <option key={b.name} value={b.name}>{b.name}</option>)}
                </select>
              </div>
            )}

            {/* Magic Auto sliders */}
            {playSettings.mode === 'Magic Auto' && (
              <div className="flex flex-col gap-2">
                <div className="console-label">MAGIC AUTO</div>
                {[
                  { key: 'brightness',       label: 'Helligkeit',   color: 'var(--accent-amber)' },
                  { key: 'blinder_strength', label: 'Beat-Blinder', color: '#ff6000' },
                  { key: 'fade',             label: 'Abklingen',    color: 'var(--accent-purple)' },
                ].map(({ key, label, color }) => (
                  <div key={key} className="flex items-center gap-2">
                    <span style={{ fontSize: 9, width: 80, color: 'var(--console-label)' }}>{label}</span>
                    <input type="range" min={0} max={1} step={0.01}
                      value={(magicAuto[key] as number) ?? 0}
                      onChange={e => setMagicAuto(key, parseFloat(e.target.value))}
                      className="flex-1"
                      style={{ accentColor: color }}
                    />
                  </div>
                ))}
              </div>
            )}

            {/* Flash automatik */}
            {playSettings.mode !== 'Magic Auto' && (
              <label className="flex items-center gap-2 cursor-pointer" style={{ marginTop: 'auto' }}>
                <input type="checkbox" checked={playSettings.flash_automatik}
                  onChange={e => post('/audio/play_settings', { flash_automatik: e.target.checked })}
                  style={{ accentColor: 'var(--accent-amber)', width: 14, height: 14 }} />
                <span style={{ fontSize: 10, fontWeight: 900, color: 'var(--accent-amber)', letterSpacing: '0.1em' }}>
                  FLASH AUTOMATIK
                </span>
              </label>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
