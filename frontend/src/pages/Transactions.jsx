import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RotateCcw, RefreshCcw, XCircle, Workflow } from 'lucide-react'
import api from '../lib/api'
import { StatusBadge, fmtTime } from '../components/UI'
import { useProject } from '../lib/ProjectContext'
import { useToast } from '../lib/ToastContext'
import '../tx-console.css'

const NON_TERMINAL = ['received', 'queued', 'processing', 'publishing']

function payloadOf(t) {
  return t?.payload && typeof t.payload === 'object' ? t.payload : {}
}
function headerOf(t) {
  return payloadOf(t).ChangeEventHeader || {}
}
function recordId(t) {
  const p = payloadOf(t)
  const h = headerOf(t)
  return (
    p.ContentDocumentId ||
    p.LinkedEntityId ||
    p.Id ||
    (Array.isArray(h.recordIds) ? h.recordIds[0] : null) ||
    t.parent_transaction_id ||
    t.id
  )
}
function groupTitle(t) {
  const p = payloadOf(t)
  if (p.ContentDocumentId) return `File ${String(p.ContentDocumentId).slice(0, 15)}…`
  return `${shortChannel(t.channel)} ${String(recordId(t)).slice(0, 12)}…`
}
function shortChannel(ch) {
  if (!ch) return 'event'
  return String(ch).replace(/^\/data\//, '').replace(/^\/event\//, '')
}
function isUserLink(t) {
  return String(payloadOf(t).LinkedEntityId || '').startsWith('005')
}

export default function Transactions() {
  const navigate = useNavigate()
  const { projectId, project } = useProject()
  const { toast } = useToast()
  const [orgs, setOrgs] = useState([])
  const [rows, setRows] = useState([])
  const [filters, setFilters] = useState({ org_id: '', channel: '', window: '3600', hideSkipped: true })
  const [selectedId, setSelectedId] = useState(null)
  const [groupTab, setGroupTab] = useState('pipeline')
  const [inspTab, setInspTab] = useState('result')
  const [reprocessingId, setReprocessingId] = useState(null)
  const [cancellingId, setCancellingId] = useState(null)
  const [bulkBusy, setBulkBusy] = useState(false)

  async function load() {
    const params = { limit: 300 }
    if (projectId) params.project_id = projectId
    if (filters.org_id) params.org_id = filters.org_id
    const [o, t] = await Promise.all([
      api.get('/orgs', { params: projectId ? { project_id: projectId } : {} }),
      api.get('/transactions', { params }),
    ])
    setOrgs(o.data || [])
    setRows(t.data || [])
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [filters.org_id, projectId])

  const channels = useMemo(() => [...new Set(rows.map((r) => r.channel).filter(Boolean))].sort(), [rows])
  const visible = useMemo(() => {
    const now = Date.now() / 1000
    const win = Number(filters.window || 0)
    return rows.filter((r) => {
      if (filters.channel && r.channel !== filters.channel) return false
      if (filters.hideSkipped && r.status === 'skipped') return false
      if (win && r.created_at && now - r.created_at > win) return false
      return true
    })
  }, [rows, filters])
  // If the user has explicitly picked a transaction (selectedId set) but a
  // refresh/filter change has aged it out of `visible`, fall back to null
  // (shows "Nothing selected") rather than silently jumping the Inspector -
  // and its Reprocess/Cancel buttons - to an arbitrary, unrelated row.
  const selectedFromList = visible.find((r) => r.id === selectedId) || null
  const selected = selectedId ? selectedFromList : visible[0] || null
  const related = useMemo(() => {
    if (!selected) return []
    const key = recordId(selected)
    return visible.filter((r) => recordId(r) === key && r.org_id === selected.org_id)
  }, [visible, selected])

  function openFlow(t) {
    if (!t) return
    if (t.event_id && t.pipeline_id) navigate(`/events/${t.event_id}/pipelines/${t.pipeline_id}/flow`)
    else if (t.event_id) navigate(`/events/${t.event_id}/pipelines`)
  }
  async function reprocess(t) {
    setReprocessingId(t.id)
    try {
      await api.post(`/transactions/${t.id}/reprocess`)
      toast(`Requeued ${t.id.slice(0, 8)}…`)
      await load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Failed to requeue', { kind: 'error' })
    } finally { setReprocessingId(null) }
  }
  async function cancel(t) {
    setCancellingId(t.id)
    try {
      const { data } = await api.post(`/transactions/${t.id}/cancel`)
      toast(data.detail || 'Cancel requested')
      await load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Failed to cancel', { kind: 'error' })
    } finally { setCancellingId(null) }
  }
  async function reprocessAllFailed() {
    if (!confirm('Requeue every failed transaction?')) return
    setBulkBusy(true)
    try {
      const { data } = await api.post('/transactions/reprocess-failed', null, {
        params: filters.org_id ? { org_id: filters.org_id } : {},
      })
      toast(data.detail)
      await load()
    } finally { setBulkBusy(false) }
  }
  const watching = [filters.org_id && '1 org', filters.channel && '1 channel'].filter(Boolean).join(' · ')

  return (
    <div className="tx-console">
      <div className="page-title-row">
        <div>
          <h1>Transactions</h1>
          <p>{project ? `${project.name} · live stream` : 'Watch inbound events by org and channel'}</p>
        </div>
        <button className="btn btn-sm" onClick={reprocessAllFailed} disabled={bulkBusy}>
          <RefreshCcw size={13} /> {bulkBusy ? 'Requeuing…' : 'Reprocess all failed'}
        </button>
      </div>
      <div className="tx-grid">
        <aside className="tx-pane">
          <div className="tx-pane-h">Stream</div>
          <div className="tx-filters">
            <select value={filters.org_id} onChange={(e) => setFilters({ ...filters, org_id: e.target.value })}>
              <option value="">All orgs</option>
              {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
            <select value={filters.channel} onChange={(e) => setFilters({ ...filters, channel: e.target.value })}>
              <option value="">All channels</option>
              {channels.map((c) => <option key={c} value={c}>{shortChannel(c)}</option>)}
            </select>
            <select value={filters.window} onChange={(e) => setFilters({ ...filters, window: e.target.value })}>
              <option value="900">Last 15m</option>
              <option value="3600">Last 1h</option>
              <option value="86400">Last 24h</option>
              <option value="">All time</option>
            </select>
            <label className="tx-check">
              <input type="checkbox" checked={filters.hideSkipped} onChange={(e) => setFilters({ ...filters, hideSkipped: e.target.checked })} />
              Hide skipped
            </label>
          </div>
          {watching && <div className="tx-watch">Watching {watching}</div>}
          <div className="tx-stream">
            {visible.length === 0 && <div className="empty-state">No transactions match</div>}
            {visible.map((t) => (
              <button key={t.id} type="button" className={`tx-row ${selected?.id === t.id ? 'active' : ''}`} onClick={() => { setSelectedId(t.id); setInspTab(t.error ? 'error' : t.result ? 'result' : 'payload') }}>
                <div className="tx-row-top"><span className="mono tx-time">{fmtTime(t.created_at)}</span><StatusBadge status={t.status} /></div>
                <div className="tx-row-ch">{shortChannel(t.channel)}</div>
                <div className="tx-row-org">{t.org_name || t.org_id}</div>
              </button>
            ))}
          </div>
        </aside>
        <section className="tx-pane">
          <div className="tx-pane-h">{selected ? `${groupTitle(selected)} · ${selected.org_name || ''}` : 'Event group'}</div>
          {selected ? (
            <>
              <div className="tx-tabs">
                <button type="button" className={groupTab === 'related' ? 'on' : ''} onClick={() => setGroupTab('related')}>Related events</button>
                <button type="button" className={groupTab === 'pipeline' ? 'on' : ''} onClick={() => setGroupTab('pipeline')}>Pipeline run</button>
              </div>
              {groupTab === 'related' ? (
                <div className="tx-related">
                  {related.map((t) => (
                    <button key={t.id} type="button" className={`tx-rel ${selected.id === t.id ? 'active' : ''}`} onClick={() => setSelectedId(t.id)}>
                      <div>
                        <strong>{shortChannel(t.channel)}</strong>
                        <div className="muted">{isUserLink(t) ? 'User library link (005)' : (payloadOf(t).LinkedEntityId || recordId(t))}</div>
                      </div>
                      <StatusBadge status={t.status} />
                    </button>
                  ))}
                </div>
              ) : (
                <ol className="tx-steps">
                  <li className="ok"><span>1</span><div><strong>Source</strong><div className="muted">{shortChannel(selected.channel)} received</div></div></li>
                  <li className={selected.status === 'skipped' ? 'ok' : 'ok'}><span>2</span><div><strong>Gate</strong><div className="muted">{selected.status === 'skipped' ? 'skipped' : 'passed / not configured'}</div></div></li>
                  <li className={selected.status === 'failed' ? 'bad' : 'ok'}><span>3</span><div><strong>Processor</strong><div className="muted">{selected.pipeline_name || 'Default processing'} · {selected.status}</div></div></li>
                  <li className={selected.status === 'published' || selected.status === 'processed' ? 'ok' : 'wait'}><span>4</span><div><strong>Publish / integrations</strong><div className="muted">{selected.status === 'failed' ? 'on_failure path' : selected.status}</div></div></li>
                  <li className={!NON_TERMINAL.includes(selected.status) ? 'ok' : 'wait'}><span>5</span><div><strong>Stop</strong><div className="muted">terminal {selected.status}</div></div></li>
                </ol>
              )}
            </>
          ) : <div className="empty-state">Select a transaction in the stream</div>}
        </section>
        <aside className="tx-pane">
          <div className="tx-pane-h">Inspector</div>
          {selected ? (
            <>
              <div className="tx-tabs">
                <button type="button" className={inspTab === 'payload' ? 'on' : ''} onClick={() => setInspTab('payload')}>Payload</button>
                <button type="button" className={inspTab === 'result' ? 'on' : ''} onClick={() => setInspTab('result')}>Result</button>
                <button type="button" className={inspTab === 'error' ? 'on' : ''} onClick={() => setInspTab('error')}>Error</button>
              </div>
              <div className="tx-meta">
                <div><label>Org</label>{selected.org_name || '—'}</div>
                <div><label>Pipeline</label>{selected.pipeline_name || '—'}</div>
                <div><label>Status</label><StatusBadge status={selected.status} /></div>
              </div>
              <pre className="tx-json">
                {inspTab === 'error' ? (selected.error || 'No error') : JSON.stringify(inspTab === 'result' ? (selected.result || { note: 'No result yet' }) : selected.payload, null, 2)}
              </pre>
              <div className="tx-actions">
                <button className="btn btn-sm" onClick={() => reprocess(selected)} disabled={reprocessingId === selected.id}><RotateCcw size={13} /> Reprocess</button>
                <button className="btn btn-sm" onClick={() => openFlow(selected)} disabled={!selected.event_id}><Workflow size={13} /> Open flow</button>
                {NON_TERMINAL.includes(selected.status) && (
                  <button className="btn btn-sm btn-danger" onClick={() => cancel(selected)} disabled={cancellingId === selected.id}><XCircle size={13} /> Cancel</button>
                )}
              </div>
            </>
          ) : <div className="empty-state">Nothing selected</div>}
        </aside>
      </div>
    </div>
  )
}
