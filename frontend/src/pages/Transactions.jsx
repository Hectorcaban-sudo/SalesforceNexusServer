import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { RotateCcw, RefreshCcw, XCircle, Workflow, ScrollText } from 'lucide-react'
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
  return p.ContentDocumentId || p.LinkedEntityId || p.Id || (Array.isArray(h.recordIds) ? h.recordIds[0] : null) || t.parent_transaction_id || t.id
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
  const [searchParams] = useSearchParams()
  const { projectId, project } = useProject()
  const { toast } = useToast()
  const [orgs, setOrgs] = useState([])
  const [rows, setRows] = useState([])
  const [filters, setFilters] = useState({ org_id: '', channel: '', window: '3600', from: '', to: '', hideSkipped: true })
  const [selectedId, setSelectedId] = useState(searchParams.get('tx'))
  const [groupTab, setGroupTab] = useState('pipeline')
  const [inspTab, setInspTab] = useState('result')
  const [reprocessingId, setReprocessingId] = useState(null)
  const [cancellingId, setCancellingId] = useState(null)
  const [bulkBusy, setBulkBusy] = useState(false)

  async function load() {
    const params = { limit: filters.window === 'custom' || !filters.window ? 1000 : 300 }
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
    const fromTs = filters.from ? Date.parse(filters.from) / 1000 : 0
    const toTs = filters.to ? Date.parse(filters.to) / 1000 + 86400 : 0
    const win = filters.window === 'custom' ? 0 : Number(filters.window || 0)
    return rows.filter((r) => {
      if (filters.channel && r.channel !== filters.channel) return false
      if (filters.hideSkipped && r.status === 'skipped') return false
      if (filters.window === 'custom') {
        if (fromTs && r.created_at < fromTs) return false
        if (toTs && r.created_at >= toTs) return false
        return true
      }
      if (win && r.created_at && now - r.created_at > win) return false
      return true
    })
  }, [rows, filters])
  const selectedFromList = visible.find((r) => r.id === selectedId) || rows.find((r) => r.id === selectedId) || null
  const selected = selectedId ? selectedFromList : visible[0] || null
  const related = useMemo(() => {
    if (!selected) return []
    const key = recordId(selected)
    return visible.filter((r) => recordId(r) === key && r.org_id === selected.org_id)
  }, [visible, selected])
  const steps = Array.isArray(selected?.result?.steps) ? selected.result.steps : []

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
      const { data } = await api.post('/transactions/reprocess-failed', null, { params: filters.org_id ? { org_id: filters.org_id } : {} })
      toast(data.detail)
      await load()
    } finally { setBulkBusy(false) }
  }
  const watching = [filters.org_id && '1 org', filters.channel && '1 channel', filters.window === 'custom' && 'custom range'].filter(Boolean).join(' · ')

  return (
    <div className="tx-console">
      <div className="page-title-row">
        <div>
          <h1>Transactions</h1>
          <p>{project ? `${project.name} · live stream` : 'Watch inbound events by org and channel'}</p>
        </div>
        <button className="btn btn-sm" onClick={reprocessAllFailed} disabled={bulkBusy}><RefreshCcw size={13} /> {bulkBusy ? 'Requeuing…' : 'Reprocess all failed'}</button>
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
              <option value="604800">Last 7d</option>
              <option value="2592000">Last 30d</option>
              <option value="custom">Custom range</option>
              <option value="">All loaded</option>
            </select>
            {filters.window === 'custom' && (
              <>
                <input type="date" value={filters.from} onChange={(e) => setFilters({ ...filters, from: e.target.value })} />
                <input type="date" value={filters.to} onChange={(e) => setFilters({ ...filters, to: e.target.value })} />
              </>
            )}
            <label className="tx-check"><input type="checkbox" checked={filters.hideSkipped} onChange={(e) => setFilters({ ...filters, hideSkipped: e.target.checked })} /> Hide skipped</label>
          </div>
          {watching && <div className="tx-watch">Watching {watching}</div>}
          <div className="tx-stream">
            {visible.length === 0 && <div className="empty-state">No transactions match</div>}
            {visible.map((t) => (
              <button key={t.id} type="button" className={`tx-row ${selected?.id === t.id ? 'active' : ''}`} onClick={() => { setSelectedId(t.id); setInspTab(t.error ? 'error' : 'result') }}>
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
                      <div><strong>{shortChannel(t.channel)}</strong><div className="muted">{isUserLink(t) ? 'User library link (005)' : (payloadOf(t).LinkedEntityId || recordId(t))}</div></div>
                      <StatusBadge status={t.status} />
                    </button>
                  ))}
                </div>
              ) : (
                <ol className="tx-steps">
                  {(selected.flow_trace || selected.result?.flow_trace || []).length > 0
                    ? (selected.flow_trace || selected.result.flow_trace).map((s, i) => (
                      <li key={s.id || i} className={s.status === 'failed' ? 'bad' : 'ok'}><span>{i + 1}</span><div><strong>{s.label || s.type}</strong><div className="muted">{s.status}</div></div></li>
                    ))
                    : (
                      <>
                        <li className="ok"><span>1</span><div><strong>Source</strong><div className="muted">{shortChannel(selected.channel)} received</div></div></li>
                        <li className={selected.status === 'failed' ? 'bad' : 'ok'}><span>2</span><div><strong>Processor</strong><div className="muted">{selected.pipeline_name || 'Default processing'} · {selected.status}</div>{steps.length > 0 && <ul className="tx-substeps">{steps.map((s, i) => <li key={i}>{s.name}{s.detail ? <div className="muted">{s.detail}</div> : null}</li>)}</ul>}</div></li>
                      </>
                    )}
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
                <button type="button" className={inspTab === 'trace' ? 'on' : ''} onClick={() => setInspTab('trace')}>Trace</button>
              </div>
              <div className="tx-meta">
                <div><label>Org</label>{selected.org_name || '—'}</div>
                <div><label>Pipeline</label>{selected.pipeline_name || '—'}</div>
                <div><label>Status</label><StatusBadge status={selected.status} /></div>
              </div>
              {inspTab === 'trace' ? <TracePane tx={selected} /> : (
                <pre className="tx-json">{inspTab === 'error' ? (selected.error || 'No error') : JSON.stringify(inspTab === 'result' ? (selected.result || { note: 'No result yet' }) : selected.payload, null, 2)}</pre>
              )}
              <div className="tx-actions">
                <button className="btn btn-sm" onClick={() => reprocess(selected)} disabled={reprocessingId === selected.id}><RotateCcw size={13} /> Reprocess</button>
                <button className="btn btn-sm" onClick={() => openFlow(selected)} disabled={!selected.event_id}><Workflow size={13} /> Open flow</button>
                <button className="btn btn-sm" onClick={() => navigate(`/logs?tx=${encodeURIComponent(selected.id)}`)}><ScrollText size={13} /> View logs</button>
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

function TracePane({ tx }) {
  const [open, setOpen] = useState(null)
  const trace = tx.flow_trace || tx.result?.flow_trace || tx.result?.steps || []
  if (!trace.length) return <div className="empty-state">No node trace on this transaction yet</div>
  return (
    <div className="tx-trace">
      {trace.map((step, i) => (
        <div key={step.id || i} className="tx-trace-step">
          <button type="button" className="tx-trace-head" onClick={() => setOpen(open === i ? null : i)}>
            <strong>{step.label || step.name || step.type}</strong>
            <span className="muted">{step.status || 'ok'}</span>
          </button>
          {open === i && (
            <div className="tx-trace-body">
              <div><label>Input</label><pre className="tx-json">{JSON.stringify(step.input || step, null, 2)}</pre></div>
              <div><label>Output</label><pre className="tx-json">{JSON.stringify(step.output || step.detail || null, null, 2)}</pre></div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
