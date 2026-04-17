const BASE = '/api'

export async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function post<T>(path: string, body?: object): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function upload(path: string, file: File): Promise<unknown> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${BASE}${path}`, { method: 'POST', body: fd })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}
