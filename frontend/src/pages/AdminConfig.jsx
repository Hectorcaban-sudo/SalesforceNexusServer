import { useEffect, useState } from 'react'
import { SlidersHorizontal, Save, CheckCircle2, CircleDashed } from 'lucide-react'
import api from '../lib/api'

const EMPTY = { url: '', project_name: '', llm: '', api_key: '' }

export default function AdminConfig() {
  const [form, setForm] = useState(EMPTY)
  const [configured, setConfigured] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState('')

  async function load() {
    const { data } = await api.get('/admin-config/dss-client')
    setForm({ url: data.url, project_name: data.project_name, llm: data.llm, api_key: '' })
    setConfigured(data.configured)
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = { ...form }
      if (!payload.api_key) delete payload.api_key // keep existing key unless a new one is entered
      const { data } = await api.put('/admin-config/dss-client', payload)
      setConfigured(data.configured)
      setForm({ url: data.url, project_name: data.project_name, llm: data.llm, api_key: '' })
      setToast('DSSClient configuration saved')
      setTimeout(() => setToast(''), 4000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Admin Configuration</h1>
          <p>Global settings used by the internal event processor — separate from per-org Salesforce connections</p>
        </div>
      </div>

      <div className="panel" style={{ maxWidth: 640 }}>
        <div className="panel-header">
          <h3><SlidersHorizontal size={15} /> DSSClient</h3>
          {configured ? (
            <span className="badge badge-green"><CheckCircle2 size={12} /> Configured</span>
          ) : (
            <span className="badge badge-gray"><CircleDashed size={12} /> Not configured</span>
          )}
        </div>
        <div className="panel-body">
          <p style={{ marginTop: 0, color: 'var(--text-secondary)', fontSize: 12.5 }}>
            When set, every inbound event is forwarded to this endpoint from <code className="pill">process_payload()</code> before
            the result is published back to Salesforce. Leave it blank to use the built-in local fallback processing instead.
          </p>

          {loading ? (
            <div className="empty-state">Loading…</div>
          ) : (
            <form onSubmit={save}>
              <div className="field">
                <label>URL</label>
                <input
                  placeholder="https://your-dss-service.example.com/api/process"
                  value={form.url}
                  onChange={(e) => setForm({ ...form, url: e.target.value })}
                />
              </div>
              <div className="form-row-2">
                <div className="field">
                  <label>Project name</label>
                  <input value={form.project_name} onChange={(e) => setForm({ ...form, project_name: e.target.value })} />
                </div>
                <div className="field">
                  <label>LLM</label>
                  <input placeholder="gpt-4, claude-sonnet-5…" value={form.llm} onChange={(e) => setForm({ ...form, llm: e.target.value })} />
                </div>
              </div>
              <div className="field">
                <label>API key</label>
                <input
                  type="password"
                  value={form.api_key}
                  onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                  placeholder={configured ? '(unchanged) enter a new key to replace it' : ''}
                />
              </div>

              {toast && <div style={{ color: 'var(--accent-green)', fontSize: 12.5, marginBottom: 12 }}>{toast}</div>}

              <button className="btn btn-primary" disabled={saving}>
                <Save size={14} /> {saving ? 'Saving…' : 'Save configuration'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
