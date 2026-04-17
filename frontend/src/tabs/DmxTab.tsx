import { useEffect, useState } from 'react'
import { get, post } from '../api/rest'
import { on } from '../api/ws'

export default function DmxTab() {
  const [ports, setPorts]           = useState<string[]>([])
  const [selectedPort, setSelectedPort] = useState('')
  const [connected, setConnected]   = useState(false)
  const [channels, setChannels]     = useState<number[]>(Array(32).fill(0))

  useEffect(() => {
    get<{ ports: string[] }>('/project/dmx/ports').then(r => {
      setPorts(r.ports)
      if (r.ports.length) setSelectedPort(r.ports[0])
    }).catch(() => {})

    get<{ connected: boolean }>('/project/dmx/status').then(r => {
      setConnected(r.connected)
    }).catch(() => {})

    const unsub = on('dmx_monitor', (p: unknown) => {
      const data = p as { channels: number[] }
      setChannels(data.channels.slice(0, 32))
    })
    return () => { unsub() }
  }, [])

  async function connect() {
    if (connected) {
      await post('/project/dmx/disconnect')
      setConnected(false)
    } else if (selectedPort) {
      try {
        await post('/project/dmx/connect', { port: selectedPort })
        setConnected(true)
      } catch (e: any) {
        alert(e.message)
      }
    }
  }

  return (
    <div className="flex flex-col h-full p-3 gap-4 overflow-y-auto" style={{ background: 'var(--console-bg)' }}>

      {/* Header */}
      <div className="flex items-center gap-4">
        <span style={{ fontSize: 13, fontWeight: 900, letterSpacing: '0.25em', color: 'var(--console-text)' }}>
          DMX INTERFACE
        </span>

        {/* Connection indicator */}
        <div className="flex items-center gap-2">
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: connected ? 'var(--accent-green)' : '#2a2a3a',
            boxShadow: connected ? '0 0 8px var(--accent-green)' : 'none',
            transition: 'all 0.2s',
          }} />
          <span style={{ fontSize: 9, letterSpacing: '0.15em', color: connected ? 'var(--accent-green)' : 'var(--console-label)' }}>
            {connected ? 'VERBUNDEN' : 'GETRENNT'}
          </span>
        </div>
      </div>

      {/* Connection panel */}
      <div className="panel" style={{ maxWidth: 480 }}>
        <div className="panel-hdr">VERBINDUNG</div>
        <div className="flex items-center gap-3 p-3">
          <select value={selectedPort} onChange={e => setSelectedPort(e.target.value)}
            className="flex-1">
            {ports.length === 0
              ? <option value="">— Kein Port gefunden —</option>
              : ports.map(p => <option key={p} value={p}>{p}</option>)
            }
          </select>
          <button onClick={connect}
            className="exec-btn" style={{
              height: 34, minWidth: 110,
              ...(connected
                ? { borderColor: 'var(--accent-red)', color: 'var(--accent-red)' }
                : { borderColor: 'var(--accent-green)', color: 'var(--accent-green)' }),
            }}>
            {connected ? 'TRENNEN' : 'VERBINDEN'}
          </button>
        </div>
      </div>

      {/* Universe monitor */}
      <div className="panel flex-1">
        <div className="panel-hdr">UNIVERSE MONITOR — CH 1–32</div>
        <div className="p-3">
          <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(16, 1fr)' }}>
            {channels.map((val, i) => (
              <div key={i} className="flex flex-col items-center gap-1">
                {/* Bar */}
                <div style={{
                  width: '100%', height: 52,
                  background: '#08080e',
                  border: '1px solid #1a1a28',
                  borderRadius: 2,
                  overflow: 'hidden',
                  display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
                }}>
                  <div style={{
                    width: '100%',
                    height: `${(val / 255) * 100}%`,
                    background: val > 200
                      ? `linear-gradient(180deg, var(--accent-red), #aa0000)`
                      : val > 100
                        ? `linear-gradient(180deg, var(--accent-amber), #aa5500)`
                        : val > 0
                          ? `linear-gradient(180deg, var(--accent-cyan), #005566)`
                          : '#1a1a28',
                    transition: 'height 0.08s',
                  }} />
                </div>
                {/* Channel number */}
                <span style={{ fontSize: 7, color: 'var(--console-label)', fontFamily: 'monospace' }}>{i + 1}</span>
                {/* Value */}
                <span style={{
                  fontSize: 8, fontWeight: 900, fontFamily: 'monospace',
                  color: val > 0 ? 'var(--console-text)' : 'var(--console-label)',
                }}>{val}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
