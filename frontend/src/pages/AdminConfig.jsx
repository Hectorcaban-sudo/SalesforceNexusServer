import { useEffect, useRef, useState } from 'react'
import {
  SlidersHorizontal, Save, CheckCircle2, CircleDashed, Upload, Trash2, Play,
  FileCode2, Download, Radio, Network, DatabaseZap, FileDown, FileUp, AlertTriangle,
  Workflow, Mail, GitFork, Plus, Pencil, Database, PlugZap,
} from 'lucide-react'
import api from '../lib/api'

const EMPTY_DSS = { url: '', project_name: '', llm: '', api_key: '' }
const EMPTY_LANGFLOW = { base_url: '', flow_id: '', api_key: '', input_field: 'input_value', output_path: '' }
const EMPTY_RMQ = { host: 'localhost', port: 5672, username: 'guest', password: '', vhost: '/', use_tls: false }
const EMPTY_EMAIL = { host: '', port: 587, username: '', password: '', use_tls: true, from_address: '' }
const EMPTY_DB = { database_type: 'sqlite', database_host: 'localhost', database_port: '', database_name: 'nexus', database_user: '', database_password: '' }

const TABS = [
  { key: 'processing', label: 'Processing mode', icon: Radio },
  { key: 'dss', label: 'DSSClient', icon: SlidersHorizontal },
  { key: 'langflow', label: 'Langflow', icon: Workflow },
  { key: 'processors', label: 'Payload processors', icon: FileCode2 },
  { key: 'rules', label: 'Rules', icon: GitFork },
  { key: 'broker', label: 'Message broker', icon: Network },
  { key: 'database', label: 'Database', icon: Database },
  { key: 'email', label: 'Email', icon: Mail },
  { key: 'backup', label: 'Configuration backup', icon: FileDown },
]

export default function AdminConfig() {
  const [tab, setTab] = useState('processing')
  const [toast, setToast] = useState('')
  const [loading, setLoading] = useState(true)

  // ---- DSSClient ----
  const [dssForm, setDssForm] = useState(EMPTY_DSS)
  const [dssConfigured, setDssConfigured] = useState(false)
  const [savingDss, setSavingDss] = useState(false)

  // ---- Langflow ----
  const [lfForm, setLfForm] = useState(EMPTY_LANGFLOW)
  const [lfConfigured, setLfConfigured] = useState(false)
  const [savingLf, setSavingLf] = useState(false)

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

  // ---- Rules ----
  const [rules, setRules] = useState([])
  const [ruleModalOpen, setRuleModalOpen] = useState(false)
  const [editingRuleId, setEditingRuleId] = useState(null)
  const [ruleForm, setRuleForm] = useState({ name: '', description: '', jdmText: '' })
  const [ruleSaving, setRuleSaving] = useState(false)
  const [ruleError, setRuleError] = useState('')
  const [ruleTestResult, setRuleTestResult] = useState(null)

  // ---- Message broker ----
  const [brokerType, setBrokerType] = useState('internal')
  const [rmqForm, setRmqForm] = useState(EMPTY_RMQ)
  const [activeBackend, setActiveBackend] = useState('internal')
  const [brokerConnError, setBrokerConnError] = useState(null)
  const [savingBroker, setSavingBroker] = useState(false)

  // ---- Email (SMTP) ----
  const [emailForm, setEmailForm] = useState(EMPTY_EMAIL)
  const [emailConfigured, setEmailConfigured] = useState(false)
  const [savingEmail, setSavingEmail] = useState(false)

  // ---- Database ----
  const [dbForm, setDbForm] = useState(EMPTY_DB)
  const [dbInfo, setDbInfo] = useState(null)
  const [savingDb, setSavingDb] = useState(false)
  const [dbTestResult, setDbTestResult] = useState(null)
  const [dbTesting, setDbTesting] = useState(false)

  // ---- Export / Import ----
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState(null)
  const importInputRef = useRef(null)

  async function load() {
    const [dss, lf, pm, procs, brk, email, rls, db] = await Promise.all([
      api.get('/admin-config/dss-client'),
      api.get('/admin-config/langflow'),
      api.get('/admin-config/processing-mode'),
      api.get('/processors'),
      api.get('/admin-config/broker'),
      api.get('/admin-config/email'),
      api.get('/rules'),
      api.get('/admin-config/database'),
    ])
    setDssForm({ url: dss.data.url, project_name: dss.data.project_name, llm: dss.data.llm, api_key: '' })
    setDssConfigured(dss.data.configured)
    setLfForm({ base_url: lf.data.base_url, flow_id: lf.data.flow_id, api_key: '', input_field: lf.data.input_field, output_path: lf.data.output_path })
    setLfConfigured(lf.data.configured)
    setMode(pm.data.mode)
    setActiveProcessorId(pm.data.active_processor_id || '')
    setProcessors(procs.data)
    setRules(rls.data)
    setBrokerType(brk.data.type)
    setRmqForm({ ...brk.data.rabbitmq, password: '' })
    setActiveBackend(brk.data.active_backend)
    setBrokerConnError(brk.data.connection_error)
    setEmailForm({ host: email.data.host, port: email.data.port, username: email.data.username, password: '', use_tls: email.data.use_tls, from_address: email.data.from_address })
    setEmailConfigured(email.data.configured)
    setDbInfo(db.data)
    setDbForm({
      database_type: db.data.database_type, database_host: db.data.database_host, database_port: db.data.database_port || '',
      database_name: db.data.database_name, database_user: db.data.database_user, database_password: '',
    })
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  function flashToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(''), 4000)
  }

  async function saveDss(e) {
    e.preventDefault()
    setSavingDss(true)
    try {
      const payload = { ...dssForm }
      if (!payload.api_key) delete payload.api_key
      const { data } = await api.put('/admin-config/dss-client', payload)
      setDssConfigured(data.configured)
      setDssForm({ url: data.url, project_name: data.project_name, llm: data.llm, api_key: '' })
      flashToast('DSSClient configuration saved')
    } finally {
      setSavingDss(false)
    }
  }

  async function saveLangflow(e) {
    e.preventDefault()
    setSavingLf(true)
    try {
      const payload = { ...lfForm }
      if (!payload.api_key) delete payload.api_key
      const { data } = await api.put('/admin-config/langflow', payload)
      setLfConfigured(data.configured)
      setLfForm({ base_url: data.base_url, flow_id: data.flow_id, api_key: '', input_field: data.input_field, output_path: data.output_path })
      flashToast('Langflow configuration saved')
    } finally {
      setSavingLf(false)
    }
  }

  async function saveMode(newMode, newActiveId) {
    setMode(newMode)
    if (newActiveId !== undefined) setActiveProcessorId(newActiveId)
    const usesId = newMode === 'custom_script' || newMode === 'rule_engine'
    await api.put('/admin-config/processing-mode', {
      mode: newMode,
      active_processor_id: usesId ? (newActiveId ?? activeProcessorId) || null : null,
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

  async function downloadProcessor(p) {
    const res = await api.get(`/processors/${p.id}/download`, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = p.filename || `${p.name}.py`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function overrideProcessor(p, file) {
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    try {
      await api.post(`/processors/${p.id}/upload`, fd)
      flashToast(`Processor "${p.name}" updated with the new file`)
      load()
    } catch (err) {
      flashToast(err?.response?.data?.detail || 'Failed to override processor')
    }
  }

  function openCreateRule() {
    setEditingRuleId(null)
    setRuleForm({ name: '', description: '', jdmText: '' })
    setRuleError('')
    setRuleTestResult(null)
    setRuleModalOpen(true)
  }

  async function openEditRule(rule) {
    const { data } = await api.get(`/rules/${rule.id}/jdm`)
    setEditingRuleId(rule.id)
    setRuleForm({ name: rule.name, description: rule.description || '', jdmText: JSON.stringify(data.jdm, null, 2) })
    setRuleError('')
    setRuleTestResult(null)
    setRuleModalOpen(true)
  }

  async function loadExampleJdm() {
    const { data } = await api.get('/rules/example')
    setRuleForm({ ...ruleForm, jdmText: JSON.stringify(data.jdm, null, 2) })
  }

  async function importJdmFile(e) {
    const file = e.target.files[0]
    if (!file) return
    const text = await file.text()
    setRuleForm({ ...ruleForm, jdmText: text })
  }

  async function saveRule(e) {
    e.preventDefault()
    setRuleError('')
    let jdm
    try {
      jdm = JSON.parse(ruleForm.jdmText)
    } catch {
      setRuleError('The decision graph is not valid JSON')
      return
    }
    setRuleSaving(true)
    try {
      if (editingRuleId) {
        await api.put(`/rules/${editingRuleId}`, { name: ruleForm.name, description: ruleForm.description, jdm })
      } else {
        await api.post('/rules', { name: ruleForm.name, description: ruleForm.description, jdm })
      }
      setRuleModalOpen(false)
      load()
    } catch (err) {
      setRuleError(err?.response?.data?.detail || 'Failed to save rule')
    } finally {
      setRuleSaving(false)
    }
  }

  async function testRuleInline(ruleId) {
    setRuleTestResult({ id: ruleId, status: 'running' })
    try {
      const { data } = await api.post(`/rules/${ruleId}/test`, { payload: { Message__c: 'test payload' } })
      setRuleTestResult({ id: ruleId, status: 'ok', detail: JSON.stringify(data.result) })
    } catch (err) {
      setRuleTestResult({ id: ruleId, status: 'fail', detail: err?.response?.data?.detail })
    }
    load()
  }

  async function removeRule(rule) {
    if (!confirm(`Delete rule "${rule.name}"? Any event channel gating on it will fall back to always processing.`)) return
    await api.delete(`/rules/${rule.id}`)
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

  async function saveEmail(e) {
    e.preventDefault()
    setSavingEmail(true)
    try {
      const payload = { ...emailForm }
      if (!payload.password) delete payload.password
      const { data } = await api.put('/admin-config/email', payload)
      setEmailConfigured(data.configured)
      setEmailForm({ host: data.host, port: data.port, username: data.username, password: '', use_tls: data.use_tls, from_address: data.from_address })
      flashToast('Email configuration saved')
    } finally {
      setSavingEmail(false)
    }
  }

  async function testDbConnection() {
    setDbTesting(true)
    setDbTestResult(null)
    try {
      const payload = { ...dbForm, database_port: dbForm.database_port ? Number(dbForm.database_port) : null }
      const { data } = await api.post('/admin-config/database/test', payload)
      setDbTestResult({ ok: true, detail: data.detail })
    } catch (err) {
      setDbTestResult({ ok: false, detail: err?.response?.data?.detail || 'Connection test failed' })
    } finally {
      setDbTesting(false)
    }
  }

  async function saveDbConfig(e) {
    e.preventDefault()
    setSavingDb(true)
    try {
      const payload = { ...dbForm, database_port: dbForm.database_port ? Number(dbForm.database_port) : null }
      if (!payload.database_password) delete payload.database_password
      const { data } = await api.put('/admin-config/database', payload)
      setDbInfo(data)
      flashToast('Database configuration saved to .env — restart the server for this to take effect')
    } catch (err) {
      flashToast(err?.response?.data?.detail || 'Failed to save database configuration')
    } finally {
      setSavingDb(false)
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

      <div className="tabs-row" style={{ padding: 0, marginBottom: 18, borderBottom: '1px solid var(--border)', paddingBottom: 14 }}>
        {TABS.map((t) => (
          <div key={t.key} className={`tab-pill ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>
            <t.icon size={13} style={{ verticalAlign: -2, marginRight: 6 }} />
            {t.label}
          </div>
        ))}
      </div>

      {loading ? <div className="empty-state">Loading…</div> : (
        <>
          {tab === 'processing' && (
            <div className="panel" style={{ maxWidth: 720 }}>
              <div className="panel-header"><h3><Radio size={15} /> Active processing mode</h3></div>
              <div className="panel-body">
                <p style={{ marginTop: 0, color: 'var(--text-secondary)', fontSize: 12.5 }}>
                  Chooses what <code className="pill">process_payload()</code> does for every inbound event, unless a
                  specific subscribed event channel overrides it (Event Configuration → Route &amp; process).
                </p>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  {['local', 'dss_client', 'langflow', 'custom_script'].map((m) => (
                    <div
                      key={m}
                      className={`tab-pill ${mode === m ? 'active' : ''}`}
                      style={{ border: '1px solid var(--border-light)', padding: '10px 16px' }}
                      onClick={() => saveMode(m)}
                    >
                      {m === 'local' && 'Local fallback'}
                      {m === 'dss_client' && 'DSSClient'}
                      {m === 'langflow' && 'Langflow'}
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
                <p style={{ marginTop: 16, color: 'var(--text-muted)', fontSize: 11.5 }}>
                  Looking for the rule engine? It's not a processing mode — it's a per-event validation gate.
                  Configure it from Event Configuration → Route &amp; process → Validation rule.
                </p>
              </div>
            </div>
          )}

          {tab === 'dss' && (
            <div className="panel" style={{ maxWidth: 720 }}>
              <div className="panel-header">
                <h3><SlidersHorizontal size={15} /> DSSClient (Dataiku DSS)</h3>
                {dssConfigured ? (
                  <span className="badge badge-green"><CheckCircle2 size={12} /> Configured</span>
                ) : (
                  <span className="badge badge-gray"><CircleDashed size={12} /> Not configured</span>
                )}
              </div>
              <div className="panel-body">
                <form onSubmit={saveDss}>
                  <div className="field">
                    <label>URL</label>
                    <input placeholder="https://your-dataiku-dss.example.com" value={dssForm.url} onChange={(e) => setDssForm({ ...dssForm, url: e.target.value })} />
                  </div>
                  <div className="form-row-2">
                    <div className="field">
                      <label>Project name</label>
                      <input value={dssForm.project_name} onChange={(e) => setDssForm({ ...dssForm, project_name: e.target.value })} />
                    </div>
                    <div className="field">
                      <label>LLM connection id</label>
                      <input value={dssForm.llm} onChange={(e) => setDssForm({ ...dssForm, llm: e.target.value })} />
                    </div>
                  </div>
                  <div className="field">
                    <label>API key</label>
                    <input type="password" value={dssForm.api_key} onChange={(e) => setDssForm({ ...dssForm, api_key: e.target.value })} placeholder={dssConfigured ? '(unchanged) enter a new key to replace it' : ''} />
                  </div>
                  <button className="btn btn-primary" disabled={savingDss}>
                    <Save size={14} /> {savingDss ? 'Saving…' : 'Save configuration'}
                  </button>
                </form>
              </div>
            </div>
          )}

          {tab === 'langflow' && (
            <div className="panel" style={{ maxWidth: 720 }}>
              <div className="panel-header">
                <h3><Workflow size={15} /> Langflow</h3>
                {lfConfigured ? (
                  <span className="badge badge-green"><CheckCircle2 size={12} /> Configured</span>
                ) : (
                  <span className="badge badge-gray"><CircleDashed size={12} /> Not configured</span>
                )}
              </div>
              <div className="panel-body">
                <p style={{ marginTop: 0, color: 'var(--text-secondary)', fontSize: 12.5 }}>
                  Calls a Langflow flow's <code className="pill">/api/v1/run/&#123;flow_id&#125;</code> endpoint with the
                  event payload and returns its response as the processing result.
                </p>
                <form onSubmit={saveLangflow}>
                  <div className="field">
                    <label>Base URL</label>
                    <input required placeholder="http://localhost:7860" value={lfForm.base_url} onChange={(e) => setLfForm({ ...lfForm, base_url: e.target.value })} />
                  </div>
                  <div className="form-row-2">
                    <div className="field">
                      <label>Flow ID</label>
                      <input required value={lfForm.flow_id} onChange={(e) => setLfForm({ ...lfForm, flow_id: e.target.value })} />
                    </div>
                    <div className="field">
                      <label>API key (optional)</label>
                      <input type="password" value={lfForm.api_key} onChange={(e) => setLfForm({ ...lfForm, api_key: e.target.value })} placeholder={lfConfigured ? '(unchanged)' : ''} />
                    </div>
                  </div>
                  <div className="form-row-2">
                    <div className="field">
                      <label>Input field name</label>
                      <input value={lfForm.input_field} onChange={(e) => setLfForm({ ...lfForm, input_field: e.target.value })} placeholder="input_value" />
                    </div>
                    <div className="field">
                      <label>Output path (optional)</label>
                      <input value={lfForm.output_path} onChange={(e) => setLfForm({ ...lfForm, output_path: e.target.value })} placeholder="Dotted path into the response, e.g. outputs.0.outputs.0.results.message.text" />
                    </div>
                  </div>
                  <button className="btn btn-primary" disabled={savingLf}>
                    <Save size={14} /> {savingLf ? 'Saving…' : 'Save configuration'}
                  </button>
                </form>
              </div>
            </div>
          )}

          {tab === 'processors' && (
            <div className="panel" style={{ maxWidth: 720 }}>
              <div className="panel-header">
                <h3><FileCode2 size={15} /> Payload processors</h3>
                <button className="btn btn-sm" onClick={downloadExample}><Download size={13} /> Download example</button>
              </div>
              <div className="panel-body">
                <p style={{ marginTop: 0, color: 'var(--text-secondary)', fontSize: 12.5 }}>
                  Upload a Python script to use as a custom processor. Contract: read one JSON object from stdin, print one
                  JSON object to stdout, and print any log messages to stderr — those show up in System Logs automatically.
                  It runs in an isolated subprocess with a 20s timeout — treat uploads like deploying
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
                            <button className="btn btn-sm btn-icon" title="Download" onClick={() => downloadProcessor(p)}><Download size={13} /></button>
                            <label className="btn btn-sm btn-icon" title="Upload a new version to override this processor" style={{ margin: 0, cursor: 'pointer' }}>
                              <FileUp size={13} />
                              <input type="file" accept=".py" style={{ display: 'none' }} onChange={(e) => overrideProcessor(p, e.target.files[0])} />
                            </label>
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
          )}

          {tab === 'rules' && (
            <div className="panel" style={{ maxWidth: 720 }}>
              <div className="panel-header">
                <h3><GitFork size={15} /> Rules (GoRules JDM / Zen Engine)</h3>
                <button className="btn btn-sm" onClick={openCreateRule}><Plus size={13} /> Add rule</button>
              </div>
              <div className="panel-body">
                <p style={{ marginTop: 0, color: 'var(--text-secondary)', fontSize: 12.5 }}>
                  A rule is a JSON Decision Model (JDM) decision graph — build one visually at{' '}
                  <a href="https://editor.gorules.io" target="_blank" rel="noreferrer" style={{ color: 'var(--accent-cyan)' }}>editor.gorules.io</a>{' '}
                  and paste/upload the exported JSON, or start from the built-in example. A rule is
                  a <strong>validation gate</strong>, not a processing mode — assign it to a subscribed event channel
                  from Event Configuration → Route &amp; process. Its output must include a boolean
                  <code className="pill" style={{ marginLeft: 4 }}>process</code> field: <code className="pill">false</code> skips
                  the event before it's ever processed. Unlike uploaded scripts, a rule is declarative data (no code
                  execution), evaluated directly against the event payload.
                </p>

                {rules.length === 0 ? (
                  <div className="empty-state">No rules created yet.</div>
                ) : (
                  <table>
                    <thead><tr><th>Name</th><th>Description</th><th>Last test</th><th></th></tr></thead>
                    <tbody>
                      {rules.map((r) => (
                        <tr key={r.id}>
                          <td>{r.name}</td>
                          <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{r.description || '—'}</td>
                          <td>
                            {r.last_status ? (
                              <span className={`badge ${r.last_status === 'ok' ? 'badge-green' : 'badge-red'}`}>
                                <span className="badge-dot" />{r.last_status}
                              </span>
                            ) : <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>never run</span>}
                          </td>
                          <td style={{ display: 'flex', gap: 6 }}>
                            <button className="btn btn-sm btn-icon" title="Edit" onClick={() => openEditRule(r)}><Pencil size={13} /></button>
                            <button className="btn btn-sm btn-icon" title="Test run" onClick={() => testRuleInline(r.id)}><Play size={13} /></button>
                            <button className="btn btn-sm btn-icon btn-danger" onClick={() => removeRule(r)}><Trash2 size={13} /></button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}

                {ruleTestResult && (
                  <div style={{ marginTop: 12, fontSize: 12, color: ruleTestResult.status === 'ok' ? 'var(--accent-green)' : ruleTestResult.status === 'fail' ? 'var(--accent-red)' : 'var(--text-muted)' }}>
                    {ruleTestResult.status === 'running' ? 'Running test…' : ruleTestResult.status === 'ok' ? `Result: ${ruleTestResult.detail}` : `Failed: ${ruleTestResult.detail}`}
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'broker' && (
            <div className="panel" style={{ maxWidth: 720 }}>
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
          )}

          {tab === 'database' && (
            <div className="panel" style={{ maxWidth: 720 }}>
              <div className="panel-header">
                <h3><Database size={15} /> Database backend</h3>
                <span className="badge badge-blue"><span className="badge-dot" />Currently running: {dbInfo?.database_type}</span>
              </div>
              <div className="panel-body">
                <p style={{ marginTop: 0, color: 'var(--text-secondary)', fontSize: 12.5 }}>
                  Choose between SQLite (default, zero setup, a local file), PostgreSQL, SQL Server, or Oracle.
                  <strong> This can't be applied live</strong> — the database is where every other setting lives, so
                  which one to connect to has to be known before the app can read anything, which means it can only
                  come from environment variables. Saving here writes those variables to the backend's <code className="pill">.env</code> file
                  and always requires a restart.
                </p>

                {dbInfo && !dbInfo.env_file_writable && (
                  <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', background: 'rgba(255,84,112,.08)', border: '1px solid rgba(255,84,112,.3)', borderRadius: 8, padding: '10px 12px', marginBottom: 14, fontSize: 12.5, color: 'var(--accent-red)' }}>
                    <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                    The .env file isn't writable from here — set these environment variables manually and restart instead.
                  </div>
                )}

                <form onSubmit={saveDbConfig}>
                  <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
                    {['sqlite', 'postgres', 'sqlserver', 'oracle'].map((t) => (
                      <div key={t} className={`tab-pill ${dbForm.database_type === t ? 'active' : ''}`} style={{ border: '1px solid var(--border-light)', padding: '10px 16px' }} onClick={() => setDbForm({ ...dbForm, database_type: t })}>
                        {t === 'sqlite' ? 'SQLite' : t === 'postgres' ? 'PostgreSQL' : t === 'sqlserver' ? 'SQL Server' : 'Oracle'}
                      </div>
                    ))}
                  </div>

                  {dbForm.database_type === 'sqlite' ? (
                    <div className="field">
                      <label>Database file path</label>
                      <div className="mono" style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{dbInfo?.db_path}</div>
                    </div>
                  ) : (
                    <>
                      <div className="form-row-2">
                        <div className="field"><label>Host</label><input required value={dbForm.database_host} onChange={(e) => setDbForm({ ...dbForm, database_host: e.target.value })} /></div>
                        <div className="field"><label>Port (optional — uses the standard port if blank)</label><input type="number" value={dbForm.database_port} onChange={(e) => setDbForm({ ...dbForm, database_port: e.target.value })} /></div>
                      </div>
                      <div className="form-row-2">
                        <div className="field"><label>{dbForm.database_type === 'sqlserver' ? 'Database' : dbForm.database_type === 'oracle' ? 'Service name' : 'Database'}</label><input required value={dbForm.database_name} onChange={(e) => setDbForm({ ...dbForm, database_name: e.target.value })} /></div>
                        <div className="field"><label>Username</label><input value={dbForm.database_user} onChange={(e) => setDbForm({ ...dbForm, database_user: e.target.value })} /></div>
                      </div>
                      <div className="field">
                        <label>Password</label>
                        <input type="password" value={dbForm.database_password} onChange={(e) => setDbForm({ ...dbForm, database_password: e.target.value })} placeholder="(unchanged) enter a new password to replace it" />
                      </div>

                      <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
                        <button type="button" className="btn" onClick={testDbConnection} disabled={dbTesting}>
                          <PlugZap size={14} /> {dbTesting ? 'Testing…' : 'Test connection'}
                        </button>
                      </div>
                      {dbTestResult && (
                        <div style={{ marginBottom: 14, fontSize: 12.5, color: dbTestResult.ok ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                          {dbTestResult.detail}
                        </div>
                      )}

                      <p style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 0 }}>
                        {dbForm.database_type === 'postgres' && 'Requires psycopg2-binary installed (pip install psycopg2-binary).'}
                        {dbForm.database_type === 'sqlserver' && 'Requires pyodbc installed, plus the OS-level "ODBC Driver 18 for SQL Server" package — see the README.'}
                        {dbForm.database_type === 'oracle' && 'Requires oracledb installed (pip install oracledb) — pure Python, no separate Oracle client needed.'}
                      </p>
                    </>
                  )}

                  <button className="btn btn-primary" disabled={savingDb || dbForm.database_type === 'sqlite'}>
                    <Save size={14} /> {savingDb ? 'Saving…' : 'Save to .env (restart required)'}
                  </button>
                  {dbForm.database_type === 'sqlite' && (
                    <p style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 8 }}>
                      SQLite is the active default — nothing to save unless you're switching to a different backend.
                    </p>
                  )}
                </form>
              </div>
            </div>
          )}

          {tab === 'email' && (
            <div className="panel" style={{ maxWidth: 720 }}>
              <div className="panel-header">
                <h3><Mail size={15} /> Email (SMTP)</h3>
                {emailConfigured ? (
                  <span className="badge badge-green"><CheckCircle2 size={12} /> Configured</span>
                ) : (
                  <span className="badge badge-gray"><CircleDashed size={12} /> Not configured</span>
                )}
              </div>
              <div className="panel-body">
                <p style={{ marginTop: 0, color: 'var(--text-secondary)', fontSize: 12.5 }}>
                  Used by any "Email" integration sink (for normal transaction fan-out or as an alert
                  delivery channel) to send mail via SMTP.
                </p>
                <form onSubmit={saveEmail}>
                  <div className="form-row-2">
                    <div className="field">
                      <label>SMTP host</label>
                      <input required value={emailForm.host} onChange={(e) => setEmailForm({ ...emailForm, host: e.target.value })} placeholder="smtp.example.com" />
                    </div>
                    <div className="field">
                      <label>Port</label>
                      <input required type="number" value={emailForm.port} onChange={(e) => setEmailForm({ ...emailForm, port: Number(e.target.value) })} />
                    </div>
                  </div>
                  <div className="form-row-2">
                    <div className="field">
                      <label>Username (optional)</label>
                      <input value={emailForm.username} onChange={(e) => setEmailForm({ ...emailForm, username: e.target.value })} />
                    </div>
                    <div className="field">
                      <label>Password (optional)</label>
                      <input type="password" value={emailForm.password} onChange={(e) => setEmailForm({ ...emailForm, password: e.target.value })} placeholder={emailConfigured ? '(unchanged)' : ''} />
                    </div>
                  </div>
                  <div className="form-row-2">
                    <div className="field">
                      <label>From address</label>
                      <input required value={emailForm.from_address} onChange={(e) => setEmailForm({ ...emailForm, from_address: e.target.value })} placeholder="nexus@yourcompany.com" />
                    </div>
                    <div className="field" style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 22 }}>
                      <input type="checkbox" style={{ width: 16 }} checked={emailForm.use_tls} onChange={(e) => setEmailForm({ ...emailForm, use_tls: e.target.checked })} />
                      <label style={{ margin: 0 }}>Use STARTTLS</label>
                    </div>
                  </div>
                  <button className="btn btn-primary" disabled={savingEmail}>
                    <Save size={14} /> {savingEmail ? 'Saving…' : 'Save configuration'}
                  </button>
                </form>
              </div>
            </div>
          )}

          {tab === 'backup' && (
            <div className="panel" style={{ maxWidth: 720 }}>
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
          )}
        </>
      )}

      {ruleModalOpen && (
        <div className="modal-overlay" onClick={() => setRuleModalOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()} style={{ width: 640 }}>
            <div className="panel-header"><h3><GitFork size={15} /> {editingRuleId ? 'Edit rule' : 'Add rule'}</h3></div>
            <form onSubmit={saveRule}>
              <div className="panel-body">
                <div className="field">
                  <label>Name</label>
                  <input required value={ruleForm.name} onChange={(e) => setRuleForm({ ...ruleForm, name: e.target.value })} placeholder="Amount approval rule" />
                </div>
                <div className="field">
                  <label>Description (optional)</label>
                  <input value={ruleForm.description} onChange={(e) => setRuleForm({ ...ruleForm, description: e.target.value })} />
                </div>
                <div className="field">
                  <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    Decision graph (JDM JSON)
                    <span style={{ display: 'flex', gap: 8 }}>
                      <button type="button" className="btn btn-sm" onClick={loadExampleJdm}>Load example</button>
                      <label className="btn btn-sm" style={{ margin: 0, cursor: 'pointer' }}>
                        Upload .json
                        <input type="file" accept=".json" style={{ display: 'none' }} onChange={importJdmFile} />
                      </label>
                    </span>
                  </label>
                  <textarea
                    required
                    rows={12}
                    className="mono"
                    style={{ fontSize: 11.5 }}
                    value={ruleForm.jdmText}
                    onChange={(e) => setRuleForm({ ...ruleForm, jdmText: e.target.value })}
                    placeholder="Paste JDM JSON exported from editor.gorules.io, or click Load example"
                  />
                </div>
                {ruleError && <div style={{ color: 'var(--accent-red)', fontSize: 12.5 }}>{ruleError}</div>}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setRuleModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={ruleSaving}>{ruleSaving ? 'Saving…' : editingRuleId ? 'Save changes' : 'Save rule'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
