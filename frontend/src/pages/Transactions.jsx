import { useEffect, useState } from 'react'
import { Eye, X } from 'lucide-react'
import api from '../lib/api'
import { StatusBadge, fmtTime } from '../components/UI'

export default function Transactions() {
  const [orgs, setOrgs] = useState([])
  const [rows, setRows] = useState([])
  const [filters, setFilters] = useState({ org_id: '', status: '', direction: '' })
  const [selected, setSelected] = useState(null)

  async function load() {
    const [o, t] = await Promise.all([
      api.get('/orgs'),
      api.get('/transactions', { params: Object.fromEntries(Object.entries(filters).filter(([, v]) => v)) }),
    ])
    setOrgs(o.data)
    setRows(t.data)
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters])

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Transactions</h1>
          <p>Full audit trail of every event received, processed, and published</p>
        </div>
      </div>

      <div className="toolbar">
        <div className="filter-row">
          <select value={filters.org_id} onChange={(e) => setFilters({ ...filters, org_id: e.target.value })}>
            <option value="">All orgs</option>
            {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
          <select value={filters.direction} onChange={(e) => setFilters({ ...filters, direction: e.target.value })}>
            <option value="">All directions</option>
            <option value="subscribe">Subscribe</option>
            <option value="publish">Publish</option>
          </select>
          <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
            <option value="">All statuses</option>
            {['received', 'queued', 'processing', 'processed', 'publishing', 'published', 'failed'].map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="panel">
        <table>
          <thead>
            <tr><th>Time</th><th>Org</th><th>Direction</th><th>Channel</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={6} className="empty-state">No transactions match these filters</td></tr>}
            {rows.map((t) => (
              <tr key={t.id}>
                <td className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{fmtTime(t.created_at)}</td>
                <td>{t.org_name}</td>
                <td style={{ textTransform: 'capitalize' }}>{t.direction}</td>
                <td><code className="pill">{t.channel}</code></td>
                <td><StatusBadge status={t.status} /></td>
                <td><button className="btn btn-sm btn-icon" onClick={() => setSelected(t)}><Eye size={14} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header">
              <h3>Transaction detail</h3>
              <button className="btn btn-sm btn-icon" onClick={() => setSelected(null)}><X size={14} /></button>
            </div>
            <div className="panel-body">
              <div className="field"><label>ID</label><code className="pill">{selected.id}</code></div>
              <div className="form-row-2">
                <div className="field"><label>Org</label><div>{selected.org_name}</div></div>
                <div className="field"><label>Status</label><StatusBadge status={selected.status} /></div>
              </div>
              <div className="form-row-2">
                <div className="field"><label>Direction</label><div style={{ textTransform: 'capitalize' }}>{selected.direction}</div></div>
                <div className="field"><label>Channel</label><code className="pill">{selected.channel}</code></div>
              </div>
              {selected.error && (
                <div className="field"><label>Error</label>
                  <div style={{ color: 'var(--accent-red)', fontSize: 12.5 }}>{selected.error}</div>
                </div>
              )}
              <div className="field">
                <label>Payload</label>
                <pre className="mono" style={{ background: 'var(--bg-panel-alt)', border: '1px solid var(--border-light)', borderRadius: 8, padding: 12, fontSize: 12, overflowX: 'auto' }}>
                  {JSON.stringify(selected.payload, null, 2)}
                </pre>
              </div>
              {selected.result && (
                <div className="field">
                  <label>Result</label>
                  <pre className="mono" style={{ background: 'var(--bg-panel-alt)', border: '1px solid var(--border-light)', borderRadius: 8, padding: 12, fontSize: 12, overflowX: 'auto' }}>
                    {JSON.stringify(selected.result, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
