import { useEffect, useMemo, useState, useRef, useCallback } from 'react'
import { Plus, Trash2, Send, Share2, Webhook, MessageSquare, Database, Cloud, Link2, BellOff, Mail, Pencil, Code2, Eye } from 'lucide-react'
import api from '../lib/api'
import { useProject, belongsToProject } from '../lib/ProjectContext'
import { TruncatedWithPopup } from '../components/UI'

const TYPE_META = {
  webhook: { label: 'Webhook', icon: Webhook },
  slack: { label: 'Slack', icon: MessageSquare },
  teams: { label: 'Microsoft Teams', icon: MessageSquare },
  email: { label: 'Email', icon: Mail },
  snowflake: { label: 'Snowflake', icon: Database },
  bigquery: { label: 'BigQuery', icon: Cloud },
  custom_api: { label: 'Custom API', icon: Link2 },
  sharepoint_file: { label: 'SharePoint File', icon: Cloud },
  sharepoint_list: { label: 'SharePoint List', icon: Cloud },
}

const TEMPLATE_SUPPORTED = new Set(['teams', 'slack', 'email', 'webhook', 'custom_api'])

const DEFAULT_CONFIG = {
  webhook: { url: '', secret: '' },
  slack: { webhook_url: '' },
  teams: { webhook_url: '' },
  email: { to: '', subject: '' },
  snowflake: { account: '', user: '', password: '', warehouse: '', database: '', schema: '', table: '' },
  bigquery: { project: '', dataset: '', table: '' },
  custom_api: { url: '', method: 'POST', auth_header: '' },
  sharepoint_file: { action_id: '' },
  sharepoint_list: { action_id: '' },
}

const EXAMPLE_TEMPLATES = {
  teams: `{
  "@type": "MessageCard",
  "@context": "http://schema.org/extensions",
  "themeColor": "{{ '33D685' if status == 'published' else 'FF5470' }}",
  "summary": "{{ payload.Subject__c | default('Nexus Event') }}",
  "title": "{{ result.summary | default('Salesforce Event Processed') }}",
  "sections": [{
    "facts": [
      {"name": "Opportunity", "value": "{{ payload.OpportunityName__c | default('—') }}"},
      {"name": "Amount", "value": "{{ payload.Amount__c | default('—') }}"},
      {"name": "AI Insight", "value": "{{ result.insight | default('—') }}"},
      {"name": "Status", "value": "{{ status }}"},
      {"name": "Transaction", "value": "{{ id }}"}
    ]
  }]
}`,
  slack: `{
  "blocks": [
    {
      "type": "header",
      "text": {"type": "plain_text", "text": "{{ result.summary | default('Nexus Update') }}"}
    },
    {
      "type": "section",
      "fields": [
        {"type": "mrkdwn", "text": "*Org:*\\n{{ org_name }}"},
        {"type": "mrkdwn", "text": "*Status:*\\n{{ status }}"},
        {"type": "mrkdwn", "text": "*Opportunity:*\\n{{ payload.OpportunityName__c | default('—') }}"},
        {"type": "mrkdwn", "text": "*Amount:*\\n{{ payload.Amount__c | default('—') }}"}
      ]
    }
  ]
}`,
  email: `{
  "subject": "[Nexus] {{ payload.Subject__c | default(channel) }} — {{ status }}",
  "body": "Transaction: {{ id }}\\nOrg: {{ org_name }}\\nStatus: {{ status }}\\n\\nOpportunity: {{ payload.OpportunityName__c | default('—') }}\\nAmount: {{ payload.Amount__c | default('—') }}\\n\\nAI Insight:\\n{{ result.insight | default('—') }}"
}`,
  webhook: `{{ t | tojson }}`,
  custom_api: `{
  "event_id": "{{ id }}",
  "status": "{{ status }}",
  "org": "{{ org_name }}",
  "payload": {{ payload | tojson }},
  "result": {{ result | tojson }}
}`,
}

const EMPTY = {
  name: '',
  type: 'webhook',
  enabled: true,
  trigger: 'always',
  org_id: '',
  alert_only: false,
  body_mode: 'default',
  body_template: '',
  config: DEFAULT_CONFIG.webhook,
}

export default function Integrations() {
  const { projectId, project } = useProject()
  const [orgs, setOrgs] = useState([])
  const [items, setItems] = useState([])
  const visibleItems = useMemo(
    () => (items || []).filter((row) => belongsToProject(row, projectId, project)),
    [items, projectId, project],
  )
  const [modalOpen, setModalOpen] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [spFileActions, setSpFileActions] = useState([])
  const [spListActions, setSpListActions] = useState([])

  const [preview, setPreview] = useState({ status: 'idle', rendered: null, error: null })
  const previewTimer = useRef(null)

  async function load() {
    const pid = projectId ? { project_id: projectId } : {}
    const [o, i, sf, sl] = await Promise.all([
      api.get('/orgs', { params: pid }),
      api.get('/integrations', { params: pid }),
      api.get('/sharepoint/file-actions', { params: pid }).catch(() => ({ data: [] })),
      api.get('/sharepoint/list-actions', { params: pid }).catch(() => ({ data: [] })),
    ])
    setOrgs(o.data)
    setItems(i.data)
    setSpFileActions(sf.data || [])
    setSpListActions(sl.data || [])
  }

  useEffect(() => { load() }, [projectId])

  const runPreview = useCallback(async (template) => {
    if (!template || !template.trim()) {
      setPreview({ status: 'idle', rendered: null, error: null })
      return
    }
    setPreview((p) => ({ ...p, status: 'loading' }))
    try {
      const { data } = await api.post('/integrations/preview-template', {
        body_template: template,
        sample_status: 'published',
      })
      if (data.ok) {
        setPreview({ status: 'ok', rendered: data.rendered, error: null })
      } else {
        setPreview({ status: 'error', rendered: null, error: data.error || 'Render failed' })
      }
    } catch (err) {
      setPreview({
        status: 'error',
        rendered: null,
        error: err?.response?.data?.detail || err.message || 'Preview request failed',
      })
    }
  }, [])

  useEffect(() => {
    if (!modalOpen || form.body_mode !== 'template') {
      setPreview({ status: 'idle', rendered: null, error: null })
      return
    }
    if (previewTimer.current) clearTimeout(previewTimer.current)
    previewTimer.current = setTimeout(() => runPreview(form.body_template), 450)
    return () => { if (previewTimer.current) clearTimeout(previewTimer.current) }
  }, [form.body_template, form.body_mode, modalOpen, runPreview])

  function openCreate() {
    setEditingId(null)
    setForm(EMPTY)
    setTestResult(null)
    setPreview({ status: 'idle', rendered: null, error: null })
    setModalOpen(true)
  }

  function openEdit(item) {
    setEditingId(item.id)
    setForm({
      name: item.name,
      type: item.type,
      enabled: item.enabled,
      trigger: item.trigger,
      org_id: item.org_id || '',
      alert_only: item.alert_only || false,
      body_mode: item.body_mode || 'default',
      body_template: item.body_template || '',
      config: { ...(DEFAULT_CONFIG[item.type] || {}), ...(item.config || {}) },
    })
    setTestResult(null)
    setPreview({ status: 'idle', rendered: null, error: null })
    setModalOpen(true)
  }

  function setType(type) {
    setForm({
      ...form,
      type,
      config: { ...(DEFAULT_CONFIG[type] || {}) },
      body_mode: TEMPLATE_SUPPORTED.has(type) ? form.body_mode : 'default',
      body_template: TEMPLATE_SUPPORTED.has(type) ? form.body_template : '',
    })
  }

  function setConfigField(key, value) {
    setForm({ ...form, config: { ...(form.config || {}), [key]: value } })
  }

  function loadExample() {
    const example = EXAMPLE_TEMPLATES[form.type]
    if (example) {
      setForm({ ...form, body_mode: 'template', body_template: example })
    }
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = {
        ...form,
        org_id: form.org_id || null,
        body_template: form.body_mode === 'template' ? (form.body_template || null) : null,
      }
      if (editingId) {
        const { type, ...updatable } = payload
        await api.put(`/integrations/${editingId}`, updatable)
      } else {
        await api.post('/integrations', { ...payload, project_id: projectId || undefined })
      }
      setModalOpen(false)
      load()
    } finally {
      setSaving(false)
    }
  }

  async function toggle(item) {
    await api.put(`/integrations/${item.id}`, { enabled: !item.enabled })
    load()
  }

  async function remove(item) {
    if (!confirm(`Delete integration "${item.name}"?`)) return
    await api.delete(`/integrations/${item.id}`)
    load()
  }

  async function sendTest(item) {
    setTestResult({ id: item.id, status: 'sending' })
    try {
      await api.post(`/integrations/${item.id}/test`)
      setTestResult({ id: item.id, status: 'ok' })
      load()
    } catch (err) {
      setTestResult({ id: item.id, status: 'fail', detail: err?.response?.data?.detail })
      load()
    }
  }

  function orgName(id) {
    if (!id) return 'All orgs'
    return orgs.find((o) => o.id === id)?.name || id
  }

  const showTemplateUI = TEMPLATE_SUPPORTED.has(form.type)

  function formatPreview(rendered) {
    if (rendered == null) return ''
    if (typeof rendered === 'string') return rendered
    try {
      return JSON.stringify(rendered, null, 2)
    } catch {
      return String(rendered)
    }
  }

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Integrations</h1>
          <p>Fan out every processed transaction to webhooks, chat tools, or a data warehouse</p>
        </div>
        <button className="btn btn-primary" onClick={openCreate}><Plus size={15} /> Add integration</button>
      </div>

      {visibleItems.length === 0 && <div className="panel"><div className="empty-state">No integrations configured yet.</div></div>}

      <div className="org-grid">
        {visibleItems.map((item) => {
          const Icon = TYPE_META[item.type]?.icon || Share2
          const hasTemplate = item.body_mode === 'template' && item.body_template
          return (
            <div className="panel org-card" key={item.id}>
              <div className="org-card-top">
                <div style={{ display: 'flex', gap: 10 }}>
                  <div className="ticker-icon" style={{ background: 'rgba(157,123,255,.12)', width: 34, height: 34 }}>
                    <Icon size={16} color="var(--accent-purple)" />
                  </div>
                  <div>
                    <h4>{item.name}</h4>
                    <div className="url">{TYPE_META[item.type]?.label || item.type}</div>
                  </div>
                </div>
                <span className={`badge ${item.enabled ? 'badge-green' : 'badge-gray'}`}>
                  <span className="badge-dot" />{item.enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>

              <div className="org-card-meta">
                <div>Trigger <b>{item.trigger}</b></div>
                <div>Scope <b>{orgName(item.org_id)}</b></div>
              </div>
              {item.alert_only && (
                <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 5 }}>
                  <BellOff size={12} /> Alert-only — excluded from normal transaction fan-out
                </div>
              )}
              {hasTemplate && (
                <div style={{ fontSize: 11, color: 'var(--accent-purple)', display: 'flex', alignItems: 'center', gap: 5 }}>
                  <Code2 size={12} /> Custom body template
                </div>
              )}

              {item.last_status && (
                <div style={{ fontSize: 11.5, color: item.last_status === 'ok' ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                  Last run: {item.last_status === 'ok' ? 'success' : `failed — ${item.last_error}`}
                </div>
              )}
              {item.last_result && (
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
                  Result: <TruncatedWithPopup text={item.last_result} maxLength={40} />
                </div>
              )}
              {testResult?.id === item.id && (
                <div style={{ fontSize: 11.5, color: testResult.status === 'ok' ? 'var(--accent-green)' : testResult.status === 'fail' ? 'var(--accent-red)' : 'var(--text-muted)' }}>
                  {testResult.status === 'sending' ? 'Sending test event…' : testResult.status === 'ok' ? 'Test succeeded' : `Test failed: ${testResult.detail}`}
                </div>
              )}

              <div className="org-card-actions">
                <button className="btn btn-sm" onClick={() => toggle(item)}>{item.enabled ? 'Disable' : 'Enable'}</button>
                <button className="btn btn-sm" onClick={() => openEdit(item)}><Pencil size={13} /> Edit</button>
                <button className="btn btn-sm" onClick={() => sendTest(item)}><Send size={13} /> Test</button>
                <button className="btn btn-sm btn-icon btn-danger" onClick={() => remove(item)}><Trash2 size={13} /></button>
              </div>
            </div>
          )
        })}
      </div>

      {modalOpen && (
        <div className="modal-overlay" onClick={() => setModalOpen(false)}>
          <div className="modal-box" style={{ maxWidth: form.body_mode === 'template' ? 920 : 640 }} onClick={(e) => e.stopPropagation()}>
            <div className="panel-header"><h3><Share2 size={15} /> {editingId ? 'Edit integration' : 'Add integration'}</h3></div>
            <form onSubmit={save}>
              <div className="panel-body">
                <div className="field">
                  <label>Name</label>
                  <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ops Slack channel, Snowflake events table…" />
                </div>
                <div className="field">
                  <label>Type{editingId && ' (cannot be changed after creation)'}</label>
                  <select value={form.type} onChange={(e) => setType(e.target.value)} disabled={!!editingId}>
                    {Object.entries(TYPE_META).map(([key, meta]) => (
                      <option key={key} value={key}>{meta.label}</option>
                    ))}
                  </select>
                </div>

                {form.type === 'webhook' && (
                  <>
                    <div className="field"><label>URL</label>
                      <input required value={form.config.url} onChange={(e) => setConfigField('url', e.target.value)} placeholder="https://example.com/webhook" />
                    </div>
                    <div className="field"><label>Signing secret (optional)</label>
                      <input type="password" value={form.config.secret} onChange={(e) => setConfigField('secret', e.target.value)} placeholder="Adds an X-Nexus-Signature HMAC header" />
                    </div>
                  </>
                )}

                {(form.type === 'slack' || form.type === 'teams') && (
                  <div className="field"><label>Webhook URL</label>
                    <input required value={form.config.webhook_url} onChange={(e) => setConfigField('webhook_url', e.target.value)}
                      placeholder={form.type === 'slack' ? 'https://hooks.slack.com/services/…' : 'https://outlook.office.com/webhook/…'} />
                  </div>
                )}

                {form.type === 'email' && (
                  <>
                    <div className="field"><label>To (comma-separated)</label>
                      <input required value={form.config.to} onChange={(e) => setConfigField('to', e.target.value)} placeholder="oncall@example.com, backup@example.com" />
                    </div>
                    <div className="field"><label>Subject (optional)</label>
                      <input value={form.config.subject} onChange={(e) => setConfigField('subject', e.target.value)} placeholder="Defaults to a generated subject" />
                    </div>
                    <p style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
                      Uses the SMTP server configured in Admin Configuration → Email.
                      {form.body_mode === 'template' && ' Subject can also be set from the template.'}
                    </p>
                  </>
                )}

                {form.type === 'custom_api' && (
                  <>
                    <div className="field"><label>URL</label>
                      <input required value={form.config.url} onChange={(e) => setConfigField('url', e.target.value)} />
                    </div>
                    <div className="form-row-2">
                      <div className="field"><label>Method</label>
                        <select value={form.config.method} onChange={(e) => setConfigField('method', e.target.value)}>
                          <option>POST</option><option>PUT</option><option>PATCH</option><option>GET</option>
                        </select>
                      </div>
                      <div className="field"><label>Authorization header (optional)</label>
                        <input value={form.config.auth_header} onChange={(e) => setConfigField('auth_header', e.target.value)} placeholder="Bearer sk-…" />
                      </div>
                    </div>
                  </>
                )}

                {form.type === 'sharepoint_file' && (
                  <div className="field">
                    <label>SharePoint file action</label>
                    <select required value={form.config.action_id || ''} onChange={(e) => setConfigField('action_id', e.target.value)}>
                      <option value="">Select a file action…</option>
                      {spFileActions.map((a) => (
                        <option key={a.id} value={a.id}>{a.name}</option>
                      ))}
                    </select>
                    <p style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 6 }}>
                      Configure actions under SharePoint → File actions. Runs after processing as a fan-out sink.
                    </p>
                  </div>
                )}

                {form.type === 'sharepoint_list' && (
                  <div className="field">
                    <label>SharePoint list action</label>
                    <select required value={form.config.action_id || ''} onChange={(e) => setConfigField('action_id', e.target.value)}>
                      <option value="">Select a list action…</option>
                      {spListActions.map((a) => (
                        <option key={a.id} value={a.id}>{a.name}</option>
                      ))}
                    </select>
                    <p style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 6 }}>
                      Configure actions under SharePoint → List actions. Runs after processing as a fan-out sink.
                    </p>
                  </div>
                )}

                {form.type === 'snowflake' && (
                  <>
                    <div className="form-row-2">
                      <div className="field"><label>Account</label><input required value={form.config.account} onChange={(e) => setConfigField('account', e.target.value)} /></div>
                      <div className="field"><label>Warehouse</label><input value={form.config.warehouse} onChange={(e) => setConfigField('warehouse', e.target.value)} /></div>
                    </div>
                    <div className="form-row-2">
                      <div className="field"><label>User</label><input required value={form.config.user} onChange={(e) => setConfigField('user', e.target.value)} /></div>
                      <div className="field"><label>Password</label><input required type="password" value={form.config.password} onChange={(e) => setConfigField('password', e.target.value)} /></div>
                    </div>
                    <div className="form-row-2">
                      <div className="field"><label>Database</label><input value={form.config.database} onChange={(e) => setConfigField('database', e.target.value)} /></div>
                      <div className="field"><label>Schema</label><input value={form.config.schema} onChange={(e) => setConfigField('schema', e.target.value)} /></div>
                    </div>
                    <div className="field"><label>Table</label><input required value={form.config.table} onChange={(e) => setConfigField('table', e.target.value)} /></div>
                  </>
                )}

                {form.type === 'bigquery' && (
                  <>
                    <div className="field"><label>GCP Project</label><input required value={form.config.project} onChange={(e) => setConfigField('project', e.target.value)} /></div>
                    <div className="form-row-2">
                      <div className="field"><label>Dataset</label><input required value={form.config.dataset} onChange={(e) => setConfigField('dataset', e.target.value)} /></div>
                      <div className="field"><label>Table</label><input required value={form.config.table} onChange={(e) => setConfigField('table', e.target.value)} /></div>
                    </div>
                    <p style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>Uses Application Default Credentials on the server — no key needs to be pasted here.</p>
                  </>
                )}

                <div className="form-row-2">
                  <div className="field">
                    <label>Trigger</label>
                    <select value={form.trigger} onChange={(e) => setForm({ ...form, trigger: e.target.value })}>
                      <option value="always">Always</option>
                      <option value="on_success">Only on success</option>
                      <option value="on_failure">Only on failure</option>
                    </select>
                  </div>
                  <div className="field">
                    <label>Scope</label>
                    <select value={form.org_id} onChange={(e) => setForm({ ...form, org_id: e.target.value })}>
                      <option value="">All orgs</option>
                      {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                    </select>
                  </div>
                </div>
                <div className="field" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input type="checkbox" style={{ width: 16 }} checked={form.alert_only} onChange={(e) => setForm({ ...form, alert_only: e.target.checked })} />
                  <label style={{ margin: 0 }}>Alert-only (don't include in normal per-transaction fan-out — only usable from the Alerts page)</label>
                </div>

                {showTemplateUI && (
                  <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                    <div className="field">
                      <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <Code2 size={14} /> Body template
                      </label>
                      <select
                        value={form.body_mode}
                        onChange={(e) => setForm({ ...form, body_mode: e.target.value })}
                      >
                        <option value="default">Default (built-in card / text)</option>
                        <option value="template">Custom Jinja2 template</option>
                      </select>
                    </div>

                    {form.body_mode === 'template' && (
                      <>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, alignItems: 'start' }}>
                          <div className="field" style={{ marginBottom: 0 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                              <label style={{ margin: 0 }}>Template</label>
                              <button type="button" className="btn btn-sm" onClick={loadExample}>
                                Load {TYPE_META[form.type]?.label} example
                              </button>
                            </div>
                            <textarea
                              value={form.body_template}
                              onChange={(e) => setForm({ ...form, body_template: e.target.value })}
                              rows={16}
                              spellCheck={false}
                              placeholder="Paste a Jinja2 template here…"
                              style={{
                                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                                fontSize: 12.5,
                                lineHeight: 1.45,
                                whiteSpace: 'pre',
                                tabSize: 2,
                                minHeight: 280,
                              }}
                            />
                          </div>

                          <div className="field" style={{ marginBottom: 0 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                              <label style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 5 }}>
                                <Eye size={13} /> Live preview
                              </label>
                              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                {preview.status === 'loading' && 'Rendering…'}
                                {preview.status === 'ok' && '✓ Valid'}
                                {preview.status === 'error' && '✗ Error'}
                                {preview.status === 'idle' && 'Waiting…'}
                              </span>
                            </div>
                            <div
                              style={{
                                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                                fontSize: 12,
                                lineHeight: 1.45,
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word',
                                minHeight: 280,
                                maxHeight: 360,
                                overflow: 'auto',
                                padding: '10px 12px',
                                borderRadius: 8,
                                border: '1px solid var(--border)',
                                background: preview.status === 'error'
                                  ? 'rgba(255, 84, 112, 0.06)'
                                  : 'var(--bg-elevated, rgba(0,0,0,0.15))',
                                color: preview.status === 'error' ? 'var(--accent-red)' : 'var(--text-primary)',
                              }}
                            >
                              {preview.status === 'idle' && (
                                <span style={{ color: 'var(--text-muted)' }}>Start typing a template to see a live render against sample data.</span>
                              )}
                              {preview.status === 'loading' && (
                                <span style={{ color: 'var(--text-muted)' }}>Rendering…</span>
                              )}
                              {preview.status === 'error' && (preview.error || 'Unknown error')}
                              {preview.status === 'ok' && formatPreview(preview.rendered)}
                            </div>
                          </div>
                        </div>

                        <div style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.55, marginTop: 10 }}>
                          <b>Available variables:</b>{' '}
                          <code>id</code>, <code>status</code>, <code>org_name</code>, <code>channel</code>,{' '}
                          <code>error</code>, <code>payload.*</code> (Salesforce event),{' '}
                          <code>result.*</code> (processor output), <code>t</code> (full transaction).
                          <br />
                          Use filters like <code>| default('—')</code> and <code>| tojson</code>.
                          Preview uses a fixed sample payload (Acme Corp renewal). The <b>Test</b> button sends a real request.
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : editingId ? 'Save changes' : 'Save integration'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
