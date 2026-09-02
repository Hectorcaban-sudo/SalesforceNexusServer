import { useEffect, useRef, useState } from 'react'
import {
  SlidersHorizontal, Save, CheckCircle2, CircleDashed, Upload, Trash2, Play,
  FileCode2, Download, Radio, Network, DatabaseZap, FileDown, FileUp, AlertTriangle,
} from 'lucide-react'
import api from '../lib/api'

const EMPTY_DSS = { url: '', project_name: '', llm: '', api_key: '' }
const EMPTY_RMQ = { host: 'localhost', port: 5672, username: 'guest', password: '', vhost: '/', use_tls: false }

export default function AdminConfig() {
  // ---- DSSClient ----
  const [form, setForm] = useState(EMPTY_DSS)
  const [configured, setConfigured] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState('')

  // ---- Processing mode ----
  const [mode, setMode] = useState('local')
  const [activeProcessorId, setActiveProcessorId] = useState('')

  // ---- Processors ----
  const [processors, setProcessors] = useState([])
  const [uploadName, setUploadName] = useState('')
  const [uploadFile, setUploadFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const fileInputRef = useRef(null)

  // ---- Message broker ----
  const [brokerType, setBrokerType] = useState('internal')
  const [rmqForm, setRmqForm] = useState(EMPTY_RMQ)
  const [activeBackend, setActiveBackend] = useState('internal')
  const [brokerConnError, setBrokerConnError] = useState(null)
  const [savingBroker, setSavingBroker] = useState(false)

  // ---- Export / Import ----
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState(null)
  const importInputRef = useRef(null)

  async function load() {
    const [dss, pm, procs, brk] = await Promise.all([
      api.get('/admin-config/dss-client'),
      api.get('/admin-config/processing-mode'),
      api.get('/processors'),
      api.get('/admin-config/broker'),
    ])
    setForm({ url: dss.data.url, project_name: dss.data.project_name, llm: dss.data.llm, api_key: '' })
    setConfigured(dss.data.configured)
    setMode(pm.data.mode)
    setActiveProcessorId(pm.data.active_processor_id || '')
    setProcessors(procs.data)
    setBrokerType(brk.data.type)
    setRmqForm({ ...brk.data.rabbitmq, password: '' })
    setActiveBackend(brk.data.active_backend)
    setBrokerConnError(brk.data.connection_error)
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  function flashToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(''), 4000)
  }

  async function saveDss(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = { ...form }
      if (!payload.api_key) delete payload.api_key
      const { data } = await api.put('/admin-config/dss-client', payload)
      setConfigured(data.configured)
      setForm({ url: data.url, project_name: data.project_name, llm: data.llm, api_key: '' })
      flashToast('DSSClient configuration saved')
    } finally {
      setSaving(false)
    }
  }

  async function saveMode(newMode, newActiveId) {
    setMode(newMode)
    if (newActiveId !== undefined) setActiveProcessorId(newActiveId)
    await api.put('/admin-config/processing-mode', {
      mode: newMode,
      active_processor_id: newMode === 'custom_script' ? (newActiveId ?? activeProcessorId) || null : activeProcessorId || null,
    })
    flashToast('Processing mode updated')
  }

  async function downloadExample() {
    const { data } = await api.get('/processors/example')
    const blob = new Blob([data.code], { type: 'text/x-python' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'example_processor.py'
    a.click()
    URL.revokeObjectURL(url)
  }

  async function upload(e) {
    e.preventDefault()
    if (!uploadFile) return
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('name', uploadName || uploadFile.name)
      fd.append('file', uploadFile)
      await api.post('/processors', fd)
      setUploadName('')
      setUploadFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      load()
      flashToast('Processor uploaded')
    } catch (err) {
      flashToast(err?.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  async function testProcessor(id) {
    setTestResult({ id, status: 'running' })
    try {
      const { data } = await api.post(`/processors/${id}/test`, { payload: { Message__c: 'test payload' } })
      setTestResult({ id, status: 'ok', detail: JSON.stringify(data.result) })
    } catch (err) {
      setTestResult({ id, status: 'fail', detail: err?.response?.data?.detail })
    }
    load()
  }

  async function removeProcessor(p) {
    if (!confirm(`Delete processor "${p.name}"?`)) return
    if (activeProcessorId === p.id) {
      await saveMode('local', null)
    }
    await api.delete(`/processors/${p.id}`)
    load()
  }

  async function saveBroker(e) {
    e.preventDefault()
    setSavingBroker(true)
    try {
      const payload = { type: brokerType, rabbitmq: { ...rmqForm } }
      if (!payload.rabbitmq.password) delete payload.rabbitmq.password
      const { data } = await api.put('/admin-config/broker', payload)
      setActiveBackend(data.active_backend)
      setBrokerConnError(data.connection_error)
      setRmqForm({ ...data.rabbitmq, password: '' })
      flashToast('Broker configuration saved — restart the server for this to take effect')
    } finally {
      setSavingBroker(false)
    }
  }

  async function exportConfig() {
    const { data } = await api.get('/admin-config/export')
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `nexus-config-export-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function importConfig(e) {
    const file = e.target.files[0]
    if (!file) return
    setImporting(true)
    setImportResult(null)
    try {
      const text = await file.text()
      const bundle = JSON.parse(text)
      const { data } = await api.post('/admin-config/import', bundle)
      setImportResult({ ok: true, detail: `Imported ${data.counts.orgs} org(s), ${data.counts.event_configs} event config(s), ${data.counts.integrations} integration(s)` })
    } catch (err) {
      setImportResult({ ok: false, detail: err?.response?.data?.detail || err.message })
    } finally {
      setImporting(false)
      if (importInputRef.current) importInputRef.current.value = ''
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

      {toast && <div className="login-hint" style={{ textAlign: 'left', marginBottom: 14, color: 'var(--accent-cyan)' }}>{toast}</div>}

      {/* Processing mode selector */}
      <div className="panel" style={{ maxWidth: 720, marginBottom: 16 }}>
        <div className="panel-header"><h3><Radio size={15} /> Active processing mode</h3></div>
        <div className="panel-body">
          <p style={{ marginTop: 0, color: 'var(--text-secondary)', fontSize: 12.5 }}>
            Chooses what <code className="pill">process_payload()</code> does for every inbound event. Switch anytime — it takes effect on the next event.
          </p>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {['local', 'dss_client', 'custom_script'].map((m) => (
              <div
                key={m}
                className={`tab-pill ${mode === m ? 'active' : ''}`}
                style={{ border: '1px solid var(--border-light)', padding: '10px 16px' }}
                onClick={() => saveMode(m)}
              >
                {m === 'local' && 'Local fallback'}
                {m === 'dss_client' && 'DSSClient'}
                {m === 'custom_script' && 'Custom uploaded script'}
              </div>
            ))}
          </div>
          {mode === 'custom_script' && (
            <div className="field" style={{ marginTop: 14 }}>
              <label>Active processor</label>
              <select value={activeProcessorId} onChange={(e) => saveMode('custom_script', e.target.value)}>
                <option value="">Select an uploaded processor…</option>
                {processors.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          )}
        </div>
      </div>

      {/* DSSClient config */}
      <div className="panel" style={{ maxWidth: 720, marginBottom: 16 }}>
        <div className="panel-header">
          <h3><SlidersHorizontal size={15} /> DSSClient</h3>
          {configured ? (
            <span className="badge badge-green"><CheckCircle2 size={12} /> Configured</span>
          ) : (
            <span className="badge badge-gray"><CircleDashed size={12} /> Not configured</span>
          )}
        </div>
        <div className="panel-body">
          {loading ? (
            <div className="empty-state">Loading…</div>
          ) : (
            <form onSubmit={saveDss}>
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
              <button className="btn btn-primary" disabled={saving}>
                <Save size={14} /> {saving ? 'Saving…' : 'Save configuration'}
              </button>
            </form>
          )}
        </div>
      </div>

      {/* Payload processors */}
      <div className="panel" style={{ maxWidth: 720 }}>
        <div className="panel-header">
          <h3><FileCode2 size={15} /> Payload processors</h3>
          <button className="btn btn-sm" onClick={downloadExample}><Download size={13} /> Download example</button>
        </div>
        <div className="panel-body">
          <p style={{ marginTop: 0, color: 'var(--text-secondary)', fontSize: 12.5 }}>
            Upload a Python script to use as a custom processor. Contract: read one JSON object from stdin, print one
            JSON object to stdout. It runs in an isolated subprocess with a 20s timeout — treat uploads like deploying
            server code (admin-only, trusted sources only).
          </p>

          <form onSubmit={upload} style={{ display: 'flex', gap: 10, alignItems: 'flex-end', marginBottom: 18, flexWrap: 'wrap' }}>
            <div className="field" style={{ flex: 1, minWidth: 160, marginBottom: 0 }}>
              <label>Name</label>
              <input value={uploadName} onChange={(e) => setUploadName(e.target.value)} placeholder="My processor" />
            </div>
            <div className="field" style={{ flex: 1, minWidth: 200, marginBottom: 0 }}>
              <label>File (.py)</label>
              <input ref={fileInputRef} type="file" accept=".py" onChange={(e) => setUploadFile(e.target.files[0])} />
            </div>
            <button className="btn btn-primary" disabled={uploading || !uploadFile}>
              <Upload size={14} /> {uploading ? 'Uploading…' : 'Upload'}
            </button>
          </form>

          {processors.length === 0 ? (
            <div className="empty-state">No processors uploaded yet.</div>
          ) : (
            <table>
              <thead><tr><th>Name</th><th>File</th><th>Last test</th><th></th></tr></thead>
              <tbody>
                {processors.map((p) => (
                  <tr key={p.id}>
                    <td>
                      {p.name}
                      {activeProcessorId === p.id && mode === 'custom_script' && (
                        <span className="badge badge-blue" style={{ marginLeft: 8 }}><span className="badge-dot" />Active</span>
                      )}
                    </td>
                    <td className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{p.filename}</td>
                    <td>
                      {p.last_status ? (
                        <span className={`badge ${p.last_status === 'ok' ? 'badge-green' : 'badge-red'}`}>
                          <span className="badge-dot" />{p.last_status}
                        </span>
                      ) : <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>never run</span>}
                    </td>
                    <td style={{ display: 'flex', gap: 6 }}>
                      <button className="btn btn-sm btn-icon" title="Test run" onClick={() => testProcessor(p.id)}><Play size={13} /></button>
                      <button className="btn btn-sm btn-icon btn-danger" onClick={() => removeProcessor(p)}><Trash2 size={13} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {testResult && (
            <div style={{ marginTop: 12, fontSize: 12, color: testResult.status === 'ok' ? 'var(--accent-green)' : testResult.status === 'fail' ? 'var(--accent-red)' : 'var(--text-muted)' }}>
              {testResult.status === 'running' ? 'Running test…' : testResult.status === 'ok' ? `Result: ${testResult.detail}` : `Failed: ${testResult.detail}`}
            </div>
          )}
        </div>
      </div>

      {/* Message broker */}
      <div className="panel" style={{ maxWidth: 720, marginTop: 16 }}>
        <div className="panel-header">
          <h3><Network size={15} /> Message broker</h3>
          <span className={`badge ${activeBackend === 'rabbitmq' ? 'badge-blue' : 'badge-gray'}`}>
            <span className="badge-dot" />Currently running: {activeBackend}
          </span>
        </div>
        <div className="panel-body">
          <p style={{ marginTop: 0, color: 'var(--text-secondary)', fontSize: 12.5 }}>
            Choose between the built-in in-process broker (zero setup, single instance only) or a real RabbitMQ
            server (durable, survives restarts). <strong>Changing this requires a server restart to take effect</strong> —
            saving here stores the config, it doesn't hot-swap the running broker.
          </p>

          {brokerConnError && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', background: 'rgba(255,84,112,.08)', border: '1px solid rgba(255,84,112,.3)', borderRadius: 8, padding: '10px 12px', marginBottom: 14, fontSize: 12.5, color: 'var(--accent-red)' }}>
              <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
              Last connection attempt failed, running on internal broker instead: {brokerConnError}
            </div>
          )}

          <form onSubmit={saveBroker}>
            <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
              {['internal', 'rabbitmq'].map((t) => (
                <div key={t} className={`tab-pill ${brokerType === t ? 'active' : ''}`} style={{ border: '1px solid var(--border-light)', padding: '10px 16px' }} onClick={() => setBrokerType(t)}>
                  {t === 'internal' ? 'Internal (in-process)' : 'RabbitMQ'}
                </div>
              ))}
            </div>

            {brokerType === 'rabbitmq' && (
              <>
                <div className="form-row-2">
                  <div className="field"><label>Host</label><input required value={rmqForm.host} onChange={(e) => setRmqForm({ ...rmqForm, host: e.target.value })} /></div>
                  <div className="field"><label>Port</label><input required type="number" value={rmqForm.port} onChange={(e) => setRmqForm({ ...rmqForm, port: Number(e.target.value) })} /></div>
                </div>
                <div className="form-row-2">
                  <div className="field"><label>Username</label><input value={rmqForm.username} onChange={(e) => setRmqForm({ ...rmqForm, username: e.target.value })} /></div>
                  <div className="field"><label>Password</label>
                    <input type="password" value={rmqForm.password} onChange={(e) => setRmqForm({ ...rmqForm, password: e.target.value })} placeholder="(unchanged) enter a new password to replace it" />
                  </div>
                </div>
                <div className="form-row-2">
                  <div className="field"><label>Virtual host</label><input value={rmqForm.vhost} onChange={(e) => setRmqForm({ ...rmqForm, vhost: e.target.value })} /></div>
                  <div className="field" style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 22 }}>
                    <input type="checkbox" style={{ width: 16 }} checked={rmqForm.use_tls} onChange={(e) => setRmqForm({ ...rmqForm, use_tls: e.target.checked })} />
                    <label style={{ margin: 0 }}>Use TLS (amqps)</label>
                  </div>
                </div>
              </>
            )}

            <button className="btn btn-primary" disabled={savingBroker}>
              <DatabaseZap size={14} /> {savingBroker ? 'Saving…' : 'Save broker configuration'}
            </button>
          </form>
        </div>
      </div>

      {/* Configuration backup */}
      <div className="panel" style={{ maxWidth: 720, marginTop: 16 }}>
        <div className="panel-header"><h3><FileDown size={15} /> Configuration backup</h3></div>
        <div className="panel-body">
          <p style={{ marginTop: 0, color: 'var(--text-secondary)', fontSize: 12.5 }}>
            Export every Salesforce org, event channel, and integration as a single JSON file, and import it back
            (here or on another instance). <strong>The export file contains credentials in plaintext</strong> (org
            secrets, integration API keys/webhook secrets) — handle it exactly like a credentials backup.
          </p>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button className="btn" onClick={exportConfig}><Download size={14} /> Export configuration</button>
            <button className="btn" onClick={() => importInputRef.current?.click()} disabled={importing}>
              <FileUp size={14} /> {importing ? 'Importing…' : 'Import configuration'}
            </button>
            <input ref={importInputRef} type="file" accept=".json" style={{ display: 'none' }} onChange={importConfig} />
          </div>
          {importResult && (
            <div style={{ marginTop: 12, fontSize: 12.5, color: importResult.ok ? 'var(--accent-green)' : 'var(--accent-red)' }}>
              {importResult.detail}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
