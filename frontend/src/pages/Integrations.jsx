import { useEffect, useState } from 'react'
import { Plus, Trash2, Send, Share2, Webhook, MessageSquare, Database, Cloud, Link2, BellOff, Mail } from 'lucide-react'
import api from '../lib/api'
import { TruncatedWithPopup } from '../components/UI'

const TYPE_META = {
  webhook: { label: 'Webhook', icon: Webhook },
  slack: { label: 'Slack', icon: MessageSquare },
  teams: { label: 'Microsoft Teams', icon: MessageSquare },
  email: { label: 'Email', icon: Mail },
  snowflake: { label: 'Snowflake', icon: Database },
  bigquery: { label: 'BigQuery', icon: Cloud },
  custom_api: { label: 'Custom API', icon: Link2 },
}

const DEFAULT_CONFIG = {
  webhook: { url: '', secret: '' },
  slack: { webhook_url: '' },
  teams: { webhook_url: '' },
  email: { to: '', subject: '' },
  snowflake: { account: '', user: '', password: '', warehouse: '', database: '', schema: '', table: '' },
  bigquery: { project: '', dataset: '', table: '' },
  custom_api: { url: '', method: 'POST', auth_header: '' },
}

const EMPTY = { name: '', type: 'webhook', enabled: true, trigger: 'always', org_id: '', alert_only: false, config: DEFAULT_CONFIG.webhook }

export default function Integrations() {
  const [orgs, setOrgs] = useState([])
  const [items, setItems] = useState([])
  const [modalOpen, setModalOpen] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [testResult, setTestResult] = useState(null)

  async function load() {
    const [o, i] = await Promise.all([api.get('/orgs'), api.get('/integrations')])
    setOrgs(o.data)
    setItems(i.data)
  }

  useEffect(() => { load() }, [])

  function openCreate() {
    setForm(EMPTY)
    setTestResult(null)
    setModalOpen(true)
  }

  function setType(type) {
    setForm({ ...form, type, config: DEFAULT_CONFIG[type] })
  }

  function setConfigField(key, value) {
    setForm({ ...form, config: { ...form.config, [key]: value } })
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = { ...form, org_id: form.org_id || null }
      await api.post('/integrations', payload)
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

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Integrations</h1>
          <p>Fan out every processed transaction to webhooks, chat tools, or a data warehouse</p>
        </div>
        <button className="btn btn-primary" onClick={openCreate}><Plus size={15} /> Add integration</button>
      </div>

      {items.length === 0 && <div className="panel"><div className="empty-state">No integrations configured yet.</div></div>}

      <div className="org-grid">
        {items.map((item) => {
          const Icon = TYPE_META[item.type]?.icon || Share2
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
                <button className="btn btn-sm" onClick={() => sendTest(item)}><Send size={13} /> Test</button>
                <button className="btn btn-sm btn-icon btn-danger" onClick={() => remove(item)}><Trash2 size={13} /></button>
              </div>
            </div>
          )
        })}
      </div>

      {modalOpen && (
        <div className="modal-overlay" onClick={() => setModalOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header"><h3><Share2 size={15} /> Add integration</h3></div>
            <form onSubmit={save}>
              <div className="panel-body">
                <div className="field">
                  <label>Name</label>
                  <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ops Slack channel, Snowflake events table…" />
                </div>
                <div className="field">
                  <label>Type</label>
                  <select value={form.type} onChange={(e) => setType(e.target.value)}>
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
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save integration'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
