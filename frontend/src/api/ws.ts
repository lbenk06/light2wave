/**
 * WebSocket singleton — connects to /ws and dispatches messages
 * to all registered handlers. Auto-reconnects on disconnect.
 */

type Handler = (payload: unknown) => void

const handlers = new Map<string, Set<Handler>>()
let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

function connect() {
  const url = `ws://${window.location.host}/ws`
  socket = new WebSocket(url)

  socket.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data) as { type: string; payload: unknown }
      const set = handlers.get(msg.type)
      if (set) set.forEach((fn) => fn(msg.payload))
    } catch {}
  }

  socket.onclose = () => {
    socket = null
    if (!reconnectTimer) {
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        connect()
      }, 1500)
    }
  }

  socket.onerror = () => socket?.close()
}

export function send(msg: object) {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(msg))
  }
}

export function on(type: string, handler: Handler) {
  if (!handlers.has(type)) handlers.set(type, new Set())
  handlers.get(type)!.add(handler)
  return () => handlers.get(type)?.delete(handler)
}

// Auto-connect
connect()
