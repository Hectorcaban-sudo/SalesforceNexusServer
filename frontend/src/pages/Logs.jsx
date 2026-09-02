import { useEffect, useState } from 'react'
import { Trash2, RefreshCw, X } from 'lucide-react'
import api from '../lib/api'

export default function Logs() {
  const [logs, setLogs] = useState([])
  const [level, setLevel] = useState('')
  const [search, setSearch] = useState('')
  const [auto, setAuto] = useState(true)
  const [selected, setSelected] = useState(null)

  async function load() {
    const { data } = await api.get('/logs', { params: { level: level || undefined, search: search || undefined, limit: 400 } })
    setLogs(data)
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level, search])

  useEffect(() => {
    if (!auto) return
    const id = setInterval(load, 4000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, level, search])

  async function clearAll() {
    if (!confirm('Clear all stored logs?')) return
    await api.delete('/logs')
    load()
  }

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>System Logs</h1>
          <p>Structured application logs from the CometD listener, broker, worker, publisher, and custom processors — click a row to see the full entry</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn btn-sm" onClick={load}><RefreshCw size={13} /> Refresh</button>
          <button className="btn btn-sm btn-danger" onClick={clearAll}><Trash2 size={13} /> Clear logs</button>
        </div>
      </div>

      <div className="toolbar">
        <div className="filter-row">
          <select value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="">All levels</option>
            <option value="DEBUG">Debug</option>
            <option value="INFO">Info</option>
            <option value="WARNING">Warning</option>
            <option value="ERROR">Error</option>
          </select>
          <input placeholder="Search message…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: 240 }} />
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, margin: 0 }}>
            <input type="checkbox" style={{ width: 15 }} checked={auto} onChange={(e) => setAuto(e.target.checked)} />
            Auto-refresh
          </label>
        </div>
      </div>

      <div className="panel">
        <div className="log-row" style={{ fontWeight: 700, color: 'var(--text-muted)', fontFamily: 'var(--font-sans)', fontSize: 11 }}>
          <div>TIME</div><div>LEVEL</div><div>LOGGER</div><div>MESSAGE</div>
        </div>
        <div className="scrollbox" style={{ maxHeight: 560 }}>
          {logs.length === 0 && <div className="empty-state">No log entries match this filter</div>}
          {logs.map((l) => (
            <div className="log-row log-row-clickable" key={l.id} onClick={() => setSelected(l)}>
              <div className="log-time">{new Date(l.timestamp * 1000).toLocaleTimeString()}</div>
              <div className={`log-level-${l.level}`}>{l.level}</div>
              <div className="log-logger">{l.logger}</div>
              <div className="log-msg log-msg-clip">{l.message}</div>
            </div>
          ))}
        </div>
      </div>

      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header">
              <h3 className={`log-level-${selected.level}`}>{selected.level} — Log entry</h3>
              <button className="btn btn-sm btn-icon" onClick={() => setSelected(null)}><X size={14} /></button>
            </div>
            <div className="panel-body">
              <div className="form-row-2">
                <div className="field"><label>Time</label><div className="mono">{new Date(selected.timestamp * 1000).toLocaleString()}</div></div>
                <div className="field"><label>Logger</label><code className="pill">{selected.logger}</code></div>
              </div>
              <div className="field">
                <label>Message</label>
                <pre className="mono log-detail-block">{selected.message}</pre>
              </div>
              {selected.context && Object.keys(selected.context).length > 0 && (
                <div className="field">
                  <label>Context</label>
                  <pre className="mono log-detail-block">{JSON.stringify(selected.context, null, 2)}</pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
