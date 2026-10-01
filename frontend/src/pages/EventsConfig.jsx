import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Radio, Trash2, Send, ArrowDownToLine, ArrowUpFromLine, Share2, GitBranch, Cpu, BellRing, Workflow, ChevronDown, ChevronRight } from 'lucide-react'
import api from '../lib/api'
import { useProject, belongsToProject, isGlobalResource, visibleLibraryItem } from '../lib/ProjectContext'
import { useToast } from '../lib/ToastContext'

const EMPTY = { org_id: '', channel: '', direction: 'subscribe', enabled: true, description: '', broker_topic: 'default' }

export default function EventsConfig() {
  const navigate = useNavigate()
  const { projectId, project } = useProject()
  const { toast } = useToast()
  const [orgs, setOrgs] = useState([])
  const [configs, setConfigs] = useState([])
  const [integrations, setIntegrations] = useState([])
  const [alerts, setAlerts] = useState([])
  const [modalOpen, setModalOpen] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)

  const [publishOpen, setPublishOpen] = useState(false)
  const [publishForm, setPublishForm] = useState({ org_id: '', channel: '', payload: '{\n  "Message__c": "hello"\n}' })
  const [publishResult, setPublishResult] = useState(null)

  const [routingTarget, setRoutingTarget] = useState(null)
  const [routingChannels, setRoutingChannels] = useState([])
  const [routingIntegrations, setRoutingIntegrations] = useState([])
  const [routingAlerts, setRoutingAlerts] = useState([])
  const [routingProcessingMode, setRoutingProcessingMode] = useState('')
  const [routingProcessorId, setRoutingProcessorId] = useState('')
  const [routingRuleId, setRoutingRuleId] = useState('')
  const [routingAutoPublish, setRoutingAutoPublish] = useState(true)
  const [processors, setProcessors] = useState([])
  const [rules, setRules] = useState([])
  const [savingRouting, setSavingRouting] = useState(false)
  const [collapsedOrgs, setCollapsedOrgs] = useState({})

  const visibleConfigs = useMemo(
    () => (configs || []).filter((c) => belongsToProject(c, projectId, project)),
    [configs, projectId, project],
  )
  const visibleRules = useMemo(
    () => (rules || []).filter((r) => visibleLibraryItem(r, projectId, { includeGlobal: true })),
    [rules, projectId],
  )
  const visibleProcessors = useMemo(
    () => (processors || []).filter((p) => visibleLibraryItem(p, projectId, { includeGlobal: true })),
    [processors, projectId],
  )

  async function load() {
    const pid = projectId ? { project_id: projectId } : {}
    const lib = projectId ? { project_id: projectId, include_global: true } : {}
    const [o, c, i, p, a, r] = await Promise.all([
      api.get('/orgs', { params: pid }),
      api.get('/events', { params: pid }),
      api.get('/integrations', { params: lib }),
      api.get('/processors', { params: lib }),
      api.get('/alerts', { params: pid }),
      api.get('/rules', { params: lib }),
    ])
    setOrgs(o.data)
    setConfigs(c.data)
    setIntegrations(i.data)
    setProcessors(p.data)
    setAlerts(a.data)
    setRules(r.data)
  }

  useEffect(() => { load() }, [projectId])

  function orgName(id) {
    return orgs.find((o) => o.id === id)?.name || id
  }

  function openCreate() {
    setForm({ ...EMPTY, org_id: orgs[0]?.id || '' })
    setModalOpen(true)
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post('/events', { ...form, project_id: projectId || undefined })
      toast('Channel created')
      setModalOpen(false)
      load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Failed to save channel', { kind: 'error' })
    } finally {
      setSaving(false)
    }
  }

  async function toggle(cfg) {
    try {
      await api.put(`/events/${cfg.id}`, { enabled: !cfg.enabled })
      toast(cfg.enabled ? 'Channel disabled' : 'Channel enabled')
      load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Failed to update channel', { kind: 'error' })
    }
  }

  async function remove(cfg) {
    if (!confirm(`Remove ${cfg.direction} channel "${cfg.channel}"?`)) return
    try {
      await api.delete(`/events/${cfg.id}`)
      toast('Channel removed')
      load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Failed to remove channel', { kind: 'error' })
    }
  }

  async function sendPublish(e) {
    e.preventDefault()
    setPublishResult(null)
    try {
      const payload = JSON.parse(publishForm.payload)
      const { data } = await api.post('/events/publish', { org_id: publishForm.org_id, channel: publishForm.channel, payload })
      setPublishResult({ ok: true, detail: `Published — transaction ${data.transaction_id}` })
    } catch (err) {
      setPublishResult({ ok: false, detail: err?.response?.data?.detail || err.message })
    }
  }

  function openRouting(cfg) {
    setRoutingTarget(cfg)
    setRoutingChannels(cfg.route_publish_channel_ids || [])
    setRoutingIntegrations(cfg.route_integration_ids || [])
    setRoutingAlerts(cfg.route_alert_ids || [])
    setRoutingProcessingMode(cfg.processing_mode || '')
    setRoutingProcessorId(cfg.processor_id || '')
    setRoutingRuleId(cfg.rule_id || '')
    setRoutingAutoPublish(cfg.auto_publish !== false)
  }

  function toggleInList(list, setList, id) {
    setList(list.includes(id) ? list.filter((x) => x !== id) : [...list, id])
  }

  async function saveRouting(e) {
    e.preventDefault()
    setSavingRouting(true)
    try {
      await api.put(`/events/${routingTarget.id}`, {
        route_publish_channel_ids: routingChannels,
        route_integration_ids: routingIntegrations,
        route_alert_ids: routingAlerts,
        processing_mode: routingProcessingMode || '',
        processor_id: ['custom_script', 'sharepoint_file', 'sharepoint_list'].includes(routingProcessingMode) ? routingProcessorId : '',
        rule_id: routingRuleId || '',
        auto_publish: routingAutoPublish,
      })
      toast('Routing saved')
      setRoutingTarget(null)
      load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Failed to save routing', { kind: 'error' })
    } finally {
      setSavingRouting(false)
    }
  }

  const subs = visibleConfigs.filter((c) => c.direction === 'subscribe')
  const pubs = visibleConfigs.filter((c) => c.direction === 'publish')
  const orgPublishChannels = routingTarget ? pubs.filter((p) => p.org_id === routingTarget.org_id) : []
  const routableIntegrations = integrations.filter((i) => !i.alert_only)

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Events & flows</h1>
          <p>{project ? `${project.name} · ` : ''}Channels grouped by Salesforce org. Pipelines live under each subscribe channel.</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn" onClick={() => setPublishOpen(true)}><Send size={14} /> Publish test event</button>
          <button className="btn btn-primary" onClick={openCreate} disabled={orgs.length === 0}><Plus size={15} /> Add channel</button>
        </div>
      </div>

      {orgs.length === 0 && <div className="panel"><div className="empty-state">Add a Salesforce org first, then configure its event channels here.</div></div>}

      {orgs.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {orgs.map((org) => {
            const orgSubs = visibleConfigs.filter((c) => c.org_id === org.id && c.direction === 'subscribe')
            const orgPubs = visibleConfigs.filter((c) => c.org_id === org.id && c.direction === 'publish')
            const total = orgSubs.length + orgPubs.length
            const closed = !!collapsedOrgs[org.id]
            return (
              <div className="panel" key={org.id}>
                <div
                  className="panel-header"
                  style={{ cursor: 'pointer' }}
                  onClick={() => setCollapsedOrgs((s) => ({ ...s, [org.id]: !s[org.id] }))}
                >
                  <h3>
                    {closed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                    {org.name}
                    {org.active === false && <span className="badge badge-gray" style={{ marginLeft: 8 }}>inactive</span>}
                  </h3>
                  <span className="badge badge-gray">{total} channel{total === 1 ? '' : 's'}</span>
                </div>
                {!closed && (
                  <div>
                    <div className="panel-header" style={{ borderTop: '1px solid var(--border)' }}>
                      <h3><ArrowDownToLine size={14} /> Subscribed</h3>
                    </div>
                    <table>
                      <thead><tr><th>Channel</th><th>Status</th><th></th></tr></thead>
                      <tbody>
                        {orgSubs.length === 0 && <tr><td colSpan={3} className="empty-state">No subscribe channels</td></tr>}
                        {orgSubs.map((c) => (
                          <tr key={c.id}>
                            <td>
                              <code className="pill">{c.channel}</code>
                              {c.description && <div className="muted" style={{ fontSize: 12 }}>{c.description}</div>}
                            </td>
                            <td>
                              <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, margin: 0, cursor: 'pointer' }}>
                                <input type="checkbox" style={{ width: 15 }} checked={c.enabled} onChange={() => toggle(c)} />
                                {c.enabled ? 'Enabled' : 'Disabled'}
                              </label>
                            </td>
                            <td style={{ display: 'flex', gap: 6 }}>
                              <button className="btn btn-sm btn-primary" type="button" onClick={() => navigate(`/events/${c.id}/pipelines`)}>
                                <Workflow size={12} /> Pipelines
                              </button>
                              <button className="btn btn-sm btn-icon btn-danger" type="button" onClick={() => remove(c)}><Trash2 size={13} /></button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="panel-header" style={{ borderTop: '1px solid var(--border)' }}>
                      <h3><ArrowUpFromLine size={14} /> Publish</h3>
                    </div>
                    <table>
                      <thead><tr><th>Channel</th><th>Status</th><th></th></tr></thead>
                      <tbody>
                        {orgPubs.length === 0 && <tr><td colSpan={3} className="empty-state">No publish channels</td></tr>}
                        {orgPubs.map((c) => (
                          <tr key={c.id}>
                            <td><code className="pill">{c.channel}</code></td>
                            <td>
                              <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, margin: 0, cursor: 'pointer' }}>
                                <input type="checkbox" style={{ width: 15 }} checked={c.enabled} onChange={() => toggle(c)} />
                                {c.enabled ? 'Enabled' : 'Disabled'}
                              </label>
                            </td>
                            <td>
                              <button className="btn btn-sm btn-icon btn-danger" type="button" onClick={() => remove(c)}><Trash2 size={13} /></button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )
          })}
          {visibleConfigs.length === 0 && orgs.length > 0 && (
            <p className="muted" style={{ fontSize: 13 }}>No channels in this project yet. Use Add channel.</p>
          )}
        </div>
      )}

      {modalOpen && (
        <div className="modal-overlay" onClick={() => setModalOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header"><h3><Radio size={15} /> Add event channel</h3></div>
            <form onSubmit={save}>
              <div className="panel-body">
                <div className="field">
                  <label>Salesforce org</label>
                  <select value={form.org_id} onChange={(e) => setForm({ ...form, org_id: e.target.value })} required>
                    {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label>Direction</label>
                  <select value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })}>
                    <option value="subscribe">Subscribe (receive from Salesforce)</option>
                    <option value="publish">Publish (send to Salesforce)</option>
                  </select>
                </div>
                <div className="field">
                  <label>Channel</label>
                  <input required placeholder="/event/My_Custom_Event__e" value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })} />
                </div>
                <div className="field">
                  <label>Description</label>
                  <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save channel'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {publishOpen && (
        <div className="modal-overlay" onClick={() => setPublishOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header"><h3><Send size={15} /> Publish test event</h3></div>
            <form onSubmit={sendPublish}>
              <div className="panel-body">
                <div className="field">
                  <label>Salesforce org</label>
                  <select value={publishForm.org_id} onChange={(e) => setPublishForm({ ...publishForm, org_id: e.target.value })} required>
                    <option value="">Select org…</option>
                    {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label>Channel / event API name</label>
                  <input required placeholder="My_Custom_Event__e" value={publishForm.channel} onChange={(e) => setPublishForm({ ...publishForm, channel: e.target.value })} />
                </div>
                <div className="field">
                  <label>Payload (JSON)</label>
                  <textarea rows={6} className="mono" value={publishForm.payload} onChange={(e) => setPublishForm({ ...publishForm, payload: e.target.value })} />
                </div>
                {publishResult && (
                  <div style={{ fontSize: 12.5, color: publishResult.ok ? 'var(--accent-green)' : 'var(--accent-red)' }}>{publishResult.detail}</div>
                )}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setPublishOpen(false)}>Close</button>
                <button type="submit" className="btn btn-primary">Publish</button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  )
}
