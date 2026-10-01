import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Trash2, RefreshCw, X } from 'lucide-react'
import api from '../lib/api'
import { useProject } from '../lib/ProjectContext'

const WINDOWS = [
  { id: '900', label: '15m' },
  { id: '3600', label: '1h' },
  { id: '86400', label: '24h' },
  { id: '', label: 'All' },
]

export default function Logs() {
  const navigate = useNavigate()
  const { projectId } = useProject()
  const [searchParams, setSearchParams] = useSearchParams()
  const txFilter = searchParams.get('tx') || ''
  const [logs, setLogs] = useState([])
  const [orgs, setOrgs] = useState([])
  const [level, setLevel] = useState('')
  const [search, setSearch] = useState('')
  const [orgId, setOrgId] = useState('')
  const [loggerQ, setLoggerQ] = useState('')
  const [windowSec, setWindowSec] = useState('3600')
  const [auto, setAuto] = useState(true)
  const [selected, setSelected] = useState(null)

  async function load() {
    const { data } = await api.get('/logs', {
      params: { level: level || undefined, search: search || undefined, transaction_id: txFilter || undefined, limit: 400 },
    })
    setLogs(data || [])
  }

  useEffect(() => { api.get('/orgs', { params: projectId ? { project_id: projectId } : {} }).then((r) => setOrgs(r.data || [])).catch(() => {}) }, [projectId])
  useEffect(() => { load() }, [level, search, txFilter])
  useEffect(() => {
    if (!auto) return
    const id = setInterval(load, 4000)
    return () => clearInterval(id)
  }, [auto, level, search, txFilter])

  const loggers = useMemo(() => [...new Set(logs.map((l) => l.logger).filter(Boolean))].sort(), [logs])
  const visible = useMemo(() => {
    const now = Date.now() / 1000
    const win = Number(windowSec || 0)
    return logs.filter((l) => {
      if (loggerQ && !(l.logger || '').includes(loggerQ)) return false
      if (orgId) {
        const ctx = l.context || {}
        if (ctx.org_id && ctx.org_id !== orgId && ctx.org_name !== orgId) return false
      }
      if (win && l.timestamp && now - l.timestamp > win) return false
      return true
    })
  }, [logs, loggerQ, orgId, windowSec])

  function clearTx() {
    const next = new URLSearchParams(searchParams)
    next.delete('tx')
    setSearchParams(next)
  }

  return (
    <div className="tx-console">
      <div className="page-title-row">
        <div>
          <h1>System Logs</h1>
          <p>{visible.length} of {logs.length}{txFilter ? ` · watching tx ${txFilter.slice(0, 8)}` : ''}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-sm" onClick={load}><RefreshCw size={13} /> Refresh</button>
          <button className="btn btn-sm btn-danger" onClick={async () => { if (confirm('Clear all stored logs?')) { await api.delete('/logs'); load() } }}><Trash2 size={13} /> Clear</button>
        </div>
      </div>
      <div className="toolbar" style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
        {WINDOWS.map((w) => (
          <button key={w.label} type="button" className="btn btn-sm" style={windowSec === w.id ? { borderColor: '#7eb6d6', color: '#7eb6d6' } : undefined} onClick={() => setWindowSec(w.id)}>{w.label}</button>
        ))}
        <select value={orgId} onChange={(e) => setOrgId(e.target.value)} style={{ width: 180 }}>
          <option value="">All orgs</option>
          {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
        <select value={level} onChange={(e) => setLevel(e.target.value)} style={{ width: 140 }}>
          <option value="">All levels</option>
          {['DEBUG', 'INFO', 'WARNING', 'ERROR'].map((s) => <option key={s}>{s}</option>)}
        </select>
        <select value={loggerQ} onChange={(e) => setLoggerQ(e.target.value)} style={{ width: 220 }}>
          <option value="">All loggers</option>
          {loggers.map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
        <input placeholder="Search message…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: 200 }} />
        <label className="tx-check"><input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /> Auto-refresh</label>
        {txFilter && <button type="button" className="btn btn-sm" onClick={clearTx}>tx {txFilter.slice(0, 8)}… <X size={12} /></button>}
      </div>
      <div className="tx-grid" style={{ gridTemplateColumns: '1.4fr 1fr' }}>
        <div className="tx-pane">
          <div className="tx-pane-h">Log stream</div>
          <div className="tx-stream">
            {visible.length === 0 && <div className="empty-state">No log entries match</div>}
            {visible.map((l) => (
              <button key={l.id} type="button" className={`tx-row ${selected?.id === l.id ? 'active' : ''}`} onClick={() => setSelected(l)}>
                <div className="tx-row-top">
                  <span className="mono tx-time">{new Date(l.timestamp * 1000).toLocaleTimeString()}</span>
                  <span className={`log-level-${l.level}`}>{l.level}</span>
                </div>
                <div className="tx-row-ch">{l.logger}</div>
                <div className="tx-row-org">{l.message}</div>
              </button>
            ))}
          </div>
        </div>
        <aside className="tx-pane">
          <div className="tx-pane-h">Log entry</div>
          {!selected && <div className="empty-state">Select a line</div>}
          {selected && (
            <>
              <div className="tx-meta">
                <div><label>Level</label><span className={`log-level-${selected.level}`}>{selected.level}</span></div>
                <div><label>Logger</label>{selected.logger}</div>
                <div><label>Time</label>{new Date(selected.timestamp * 1000).toLocaleString()}</div>
              </div>
              <pre className="tx-json">{selected.message}</pre>
              <pre className="tx-json">{JSON.stringify(selected.context || {}, null, 2)}</pre>
              {(selected.context?.transaction_id) && (
                <div className="tx-actions">
                  <button className="btn btn-sm" onClick={() => navigate(`/transactions?tx=${encodeURIComponent(selected.context.transaction_id)}`)}>Open transaction</button>
                </div>
              )}
            </>
          )}
        </aside>
      </div>
    </div>
  )
}
