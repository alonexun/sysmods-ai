export const TOKEN_KEY = 'sysmods_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY) || ''
export const setToken = t => localStorage.setItem(TOKEN_KEY, t)

export async function api(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Token': getToken() },
    body: body ? JSON.stringify(body) : '{}'
  })
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw Object.assign(new Error(j.detail || r.status), { status: r.status })
  return j
}

export async function getJSON(path) {
  const r = await fetch(path, { headers: { 'X-Token': getToken() } })
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw Object.assign(new Error(j.detail || r.status), { status: r.status })
  return j
}

export const money = v => {
  if (v == null) return '—'
  v = Number(v)
  if (Number.isNaN(v)) return 'NaN'
  const a = Math.abs(v)
  if (a >= 1e8) return (v / 1e8).toFixed(2) + ' 亿元'
  if (a >= 1e4) return (v / 1e4).toFixed(1) + ' 万元'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) + ' 元'
}
export const fmt = (v, n = 1) =>
  typeof v === 'number' && !Number.isNaN(v)
    ? v.toLocaleString('zh-CN', { maximumFractionDigits: n }) : (v ?? '—')
export const pct = v => typeof v === 'number' ? (v * 100).toFixed(1) + '%' : '—'
