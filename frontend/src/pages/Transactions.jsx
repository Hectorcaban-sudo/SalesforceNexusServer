import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Eye, X, RotateCcw, RefreshCcw, ChevronDown, ChevronRight, Layers, XCircle, Workflow } from 'lucide-react'
import api from '../lib/api'
import { StatusBadge, fmtTime } from '../components/UI'
import { useProject } from '../lib/ProjectContext'

const GROUP_OPTIONS = [
  { key: 'none', label: 'No grouping' },
  { key: 'org_name', label: 'Org' },
  { key: 'status', label: 'Status' },
  { key: 'direction', label: 'Direction' },
  { key: 'channel', label: 'Channel' },
  { key: 'parent_transaction_id', label: 'Fan-out group' },
  { key: 'pipeline_name', label: 'Pipeline' },
]

export default function Transactions() {
  const navigate = useNavigate()
  const { projectId, project } = useProject()
  const [orgs, setOrgs] = useState([])
  const [rows, setRows] = useState([])
  const [filters, setFilters] = useState({ org_id: '', status: '', direction: '' })
  const [groupBy, setGroupBy] = useState('none')
  const [collapsed, setCollapsed] = useState({})
  const [selected, setSelected] = useState(null)
  const [reprocessingId, setReprocessingId] = useState(null)
  const [cancellingId, setCancellingId] = useState(null)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [toast, setToast] = useState('')

  async function load() {
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))
    if (projectId) params.project_id = projectId
    const [o, t] = await Promise.all([
      api.get('/orgs', { params: projectId ? { project_id: projectId } : {} }),
      api.get('/transactions', { params }),
    ])
    setOrgs(o.data)
    setRows(t.data)
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, projectId])

  function flashToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(''), 4000)
  }

  async function reprocess(t) {
    setReprocessingId(t.id)
    try {
      await api.post(`/transactions/${t.id}/reprocess`)
      flashToast(`Requeued transaction ${t.id}`)
      await load()
      if (selected?.id === t.id) {
        const { data } = await api.get('/transactions', { params: { limit: 1 } })
        setSelected(data.find((r) => r.id === t.id) || selected)
      }
    } catch (err) {
      flashToast(err?.response?.data?.detail || 'Failed to requeue transaction')
    } finally {
      setReprocessingId(null)
    }
  }

  async function reprocessAllFailed() {
    if (!confirm('Requeue every failed transaction back through the broker?')) return
    setBulkBusy(true)
    try {
      const { data } = await api.post('/transactions/reprocess-failed', null, {
        params: filters.org_id ? { org_id: filters.org_id } : {},
      })
      flashToast(data.detail)
      await load()
    } finally {
      setBulkBusy(false)
    }
  }

  async function cancel(t) {
    if (!confirm(`Cancel transaction ${t.id}?`)) return
    setCancellingId(t.id)
    try {
      const { data } = await api.post(`/transactions/${t.id}/cancel`)
      flashToast(data.detail)
      await load()
    } catch (err) {
      flashToast(err?.response?.data?.detail || 'Failed to cancel transaction')
    } finally {
      setCancellingId(null)
    }
  }

  function toggleGroup(key) {
    setCollapsed({ ...collapsed, [key]: !collapsed[key] })
  }

  const groups = useMemo(() => {
    if (groupBy === 'none') return null
    const map = new Map()
    for (const t of rows) {
      let key = t[groupBy]
      if (groupBy === 'parent_transaction_id') key = t.parent_transaction_id || t.id  // ungrouped rows become their own singleton group
      if (key == null || key === '') key = '(none)'
      if (!map.has(key)) map.set(key, [])
      map.get(key).push(t)
    }
    // sort groups by most recent activity first
    return [...map.entries()].sort((a, b) => Math.max(...b[1].map((r) => r.created_at)) - Math.max(...a[1].map((r) => r.created_at)))
  }, [rows, groupBy])

  const treeRows = useMemo(() => {
    const ids = new Set(rows.map((r) => r.id))
    const children = new Map()
    for (const t of rows) {
      const pid = t.parent_transaction_id
      if (pid && ids.has(pid)) {
        if (!children.has(pid)) children.set(pid, [])
        children.get(pid).push(t)
      }
    }
    const out = []
    const seen = new Set()
    function walk(t, depth) {
      if (seen.has(t.id)) return
      seen.add(t.id)
      out.push({ ...t, _depth: depth, _kids: (children.get(t.id) || []).length })
      for (const c of children.get(t.id) || []) walk(c, depth + 1)
    }
    for (const t of rows) {
      const isChild = t.parent_transaction_id && ids.has(t.parent_transaction_id)
      if (!isChild) walk(t, 0)
    }
    for (const t of rows) {
      if (!seen.has(t.id)) walk(t, 0)
    }
    return out
  }, [rows])

  function openFlow(t) {
    if (t.event_id && t.pipeline_id) navigate(`/events/${t.event_id}/pipelines/${t.pipeline_id}/flow`)
    else if (t.event_id) navigate(`/events/${t.event_id}/pipelines`)
  }

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Transactions</h1>
          <p>{project ? `${project.name} · pipeline runs` : 'Audit trail of received, processed, published, and skipped (Stop) runs'}</p>
        </div>
        <button className="btn btn-sm" onClick={reprocessAllFailed} disabled={bulkBusy}>
          <RefreshCcw size={13} /> {bulkBusy ? 'Requeuing…' : 'Reprocess all failed'}
        </button>
      </div>

      {toast && <div className="login-hint" style={{ textAlign: 'left', marginBottom: 12, color: 'var(--accent-cyan)' }}>{toast}</div>}

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
            {['received', 'queued', 'processing', 'processed', 'skipped', 'publishing', 'published', 'failed'].map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <select value={groupBy} onChange={(e) => setGroupBy(e.target.value)}>
            {GROUP_OPTIONS.map((g) => <option key={g.key} value={g.key}>{g.key === 'none' ? 'Group by…' : `Group by: ${g.label}`}</option>)}
          </select>
        </div>
      </div>

      {groupBy === 'none' ? (
        <div className="panel">
          <table>
            <thead>
              <tr><th>Time</th><th>Channel</th><th>Pipeline</th><th>Status</th><th>Attempts</th><th></th></tr>
            </thead>
            <tbody>
              {treeRows.length === 0 && <tr><td colSpan={6} className="empty-state">No transactions match these filters</td></tr>}
              {treeRows.map((t) => (
                <TransactionRow key={t.id} t={t} onView={setSelected} onReprocess={reprocess} reprocessingId={reprocessingId} onCancel={cancel} cancellingId={cancellingId} onOpenFlow={openFlow} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {groups.length === 0 && <div className="panel"><div className="empty-state">No transactions match these filters</div></div>}
          {groups.map(([key, groupRows]) => (
            <div className="panel" key={key}>
              <div
                className="panel-header"
                style={{ cursor: 'pointer' }}
                onClick={() => toggleGroup(key)}
              >
                <h3>
                  {collapsed[key] ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                  <Layers size={13} style={{ marginRight: 2 }} />
                  {groupBy === 'parent_transaction_id' ? `Fan-out: ${key.slice(0, 12)}…` : String(key)}
                </h3>
                <span className="badge badge-gray">{groupRows.length} transaction{groupRows.length === 1 ? '' : 's'}</span>
              </div>
              {!collapsed[key] && (
                <table>
                  <thead>
                    <tr><th>Time</th><th>Channel</th><th>Pipeline</th><th>Status</th><th>Attempts</th><th></th></tr>
                  </thead>
                  <tbody>
                    {groupRows.map((t) => (
                      <TransactionRow key={t.id} t={t} onView={setSelected} onReprocess={reprocess} reprocessingId={reprocessingId} onCancel={cancel} cancellingId={cancellingId} onOpenFlow={openFlow} />
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ))}
        </div>
      )}

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
                <div className="field"><label>Project</label><div>{selected.project_name || '-'}</div></div>
                <div className="field"><label>Org</label><div>{selected.org_name}</div></div>
                <div className="field"><label>Status</label><StatusBadge status={selected.status} /></div>
              </div>
              <div className="form-row-2">
                <div className="field"><label>Direction</label><div style={{ textTransform: 'capitalize' }}>{selected.direction}</div></div>
                <div className="field"><label>Channel</label><code className="pill">{selected.channel}</code></div>
              </div>
              <div className="form-row-2">
                <div className="field"><label>Pipeline</label><div>{selected.pipeline_name || (selected.result?.fanout ? `Fan-out · ${selected.result.fanout}` : '—')}</div></div>
                <div className="field"><label>Parent</label><div className="mono">{selected.parent_transaction_id || '—'}</div></div>
              </div>
              <div className="field">
                <label>Attempts</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span className="mono">{selected.attempts || 0}</span>
                  <button
                    className="btn btn-sm"
                    onClick={() => reprocess(selected)}
                    disabled={reprocessingId === selected.id}
                  >
                    <RotateCcw size={13} /> {reprocessingId === selected.id ? 'Requeuing…' : 'Reprocess'}
                  </button>
                  {NON_TERMINAL_STATUSES.includes(selected.status) && (
                    <button
                      className="btn btn-sm btn-danger"
                      onClick={() => cancel(selected)}
                      disabled={cancellingId === selected.id || selected.cancel_requested}
                    >
                      <XCircle size={13} /> {selected.cancel_requested ? 'Cancelling…' : 'Cancel'}
                    </button>
                  )}
                </div>
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

const NON_TERMINAL_STATUSES = ['received', 'queued', 'processing', 'publishing']

function TransactionRow({ t, onView, onReprocess, reprocessingId, onCancel, cancellingId, onOpenFlow }) {
  const cancellable = NON_TERMINAL_STATUSES.includes(t.status)
  const depth = t._depth || 0
  const fanout = t.result && t.result.fanout
  return (
    <tr>
      <td className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)', paddingLeft: 12 + depth * 18 }}>
        {depth > 0 ? '↳ ' : ''}{fmtTime(t.created_at)}
      </td>
      <td><code className="pill">{t.channel}</code></td>
      <td>
        {t.pipeline_name || (fanout ? `Fan-out · ${fanout} pipelines` : '—')}
      </td>
      <td>
        <StatusBadge status={t.status} />
        {t.cancel_requested && t.status !== 'cancelled' && (
          <div style={{ fontSize: 10.5, color: 'var(--accent-orange)', marginTop: 3 }}>cancelling…</div>
        )}
      </td>
      <td className="mono" style={{ color: 'var(--text-muted)' }}>{t.attempts || 0}</td>
      <td style={{ display: 'flex', gap: 6 }}>
        <button className="btn btn-sm btn-icon" onClick={() => onView(t)} title="View details"><Eye size={14} /></button>
        {t.event_id && (
          <button className="btn btn-sm btn-icon" title="Open flow" onClick={() => onOpenFlow(t)}>
            <Workflow size={14} />
          </button>
        )}
        <button
          className="btn btn-sm btn-icon"
          title="Reprocess through broker"
          onClick={() => onReprocess(t)}
          disabled={reprocessingId === t.id}
        >
          <RotateCcw size={14} className={reprocessingId === t.id ? 'spin' : ''} />
        </button>
        {cancellable && (
          <button
            className="btn btn-sm btn-icon btn-danger"
            title="Cancel"
            onClick={() => onCancel(t)}
            disabled={cancellingId === t.id || t.cancel_requested}
          >
            <XCircle size={14} />
          </button>
        )}
      </td>
    </tr>
  )
}
