import { useEffect, useState } from 'react'
import { Plus, Globe, FlaskConical, Pencil, Trash2 } from 'lucide-react'
import api from '../lib/api'
import { useToast } from '../lib/ToastContext'
import { useProject } from '../lib/ProjectContext'

const EMPTY = {
  name: '', url: '', method: 'POST', timeout: 60, verify_ssl: true,
  headers: [{ name: '', value: '' }],
  body_template: '{{ payload | tojson }}',
}

function Modal({ title, onClose, children, footer }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()} style={{ width: 680 }}>
        <div className="panel-header"><h3>{title}</h3></div>
        <div className="panel-body">{children}</div>
        <div className="modal-footer">{footer}</div>
      </div>
    </div>
  )
}

export default function Rest({ scope = 'global' }) {
  const { toast } = useToast()
  const { project, projectId } = useProject()
  const isProject = scope === 'project'
  const [processors, setProcessors] = useState([])
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [testing, setTesting] = useState(null)
  const [sample, setSample] = useState('{\n  "User_Message__c": ""\n}')
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)

  const fail = (err, fallback) => toast(err?.response?.data?.detail || err?.message || fallback, { kind: 'error' })

  async function load() {
    const params = isProject && projectId ? { project_id: projectId } : {}
    const { data } = await api.get('/rest/processors', { params })
    const rows = data || []
    setProcessors(isProject ? rows.filter((r) => r.project_id === projectId) : rows.filter((r) => !r.project_id))
  }
  useEffect(() => { load().catch((e) => fail(e, 'Failed to load REST processors')) }, [scope, projectId])

  function openNew() {
    setForm(EMPTY)
    setEditing('new')
  }
  function openEdit(p) {
    setForm({ ...EMPTY, ...p, headers: (p.headers && p.headers.length ? p.headers : [{ name: '', value: '' }]) })
    setEditing(p.id)
  }
  function openTest(p) {
    setTesting(p)
    setSample('{\n  "User_Message__c": ""\n}')
    setResult(null)
  }

  function setHeader(i, key, value) {
    setForm({ ...form, headers: form.headers.map((h, j) => j === i ? { ...h, [key]: value } : h) })
  }

  async function save(ev) {
    ev.preventDefault()
    if (isProject && !projectId) return fail(new Error('Select a project first'), 'Select a project first')
    const body = { ...form, project_id: isProject ? projectId : null, timeout: Number(form.timeout) || 60, headers: form.headers.filter((h) => h.name) }
    try {
      if (editing === 'new') await api.post('/rest/processors', body)
      else await api.put('/rest/processors/' + editing, body)
      toast(editing === 'new' ? 'Processor saved' : 'Processor updated')
      setEditing(null)
      load()
    } catch (err) { fail(err, 'Failed to save processor') }
  }

  async function remove(p) {
    if (!confirm('Delete ' + p.name + '?')) return
    try {
      await api.delete('/rest/processors/' + p.id)
      toast('Processor deleted')
      load()
    } catch (err) { fail(err, 'Delete failed') }
  }

  async function runTest(ev) {
    ev.preventDefault()
    setRunning(true)
    try {
      const payload = JSON.parse(sample || '{}')
      const { data } = await api.post('/rest/processors/' + testing.id + '/test', { payload }, { timeout: (Number(testing.timeout) || 60) * 1000 + 5000 })
      setResult(data)
      toast((data.status_code || 200) + ' OK')
    } catch (err) {
      if (err instanceof SyntaxError) fail(err, 'Sample is not valid JSON')
      else fail(err.code === 'ECONNABORTED' ? new Error('Request timed out') : err, 'Test failed')
    } finally { setRunning(false) }
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-end' }}>
        <div>
          <h1>{isProject ? 'REST processors' : 'REST processors'}</h1>
          <p className="page-sub">
            {isProject
              ? <>Processors for <strong>{project?.name || 'this project'}</strong>. Global ones are shared and edited in Administration.</>
              : 'Global. Shared by every project. A pipeline calls one like any other processor.'}
          </p>
        </div>
        <button className="btn btn-primary" onClick={openNew}><Plus size={14} /> {isProject ? 'New project processor' : 'New global processor'}</button>
      </div>

      <div className="org-grid">
        {processors.length === 0 && <div className="empty-state">None yet</div>}
        {processors.map((p) => (
          <div key={p.id} className="org-card">
            <div className="org-card-header">
              <Globe size={16} />
              <div>
                <div className="name">{p.name} <span className="badge badge-blue">{p.method || 'POST'}</span></div>
                <div className="url">{p.url}</div>
              </div>
            </div>
            <div className="org-card-actions">
              <button className="btn btn-sm" onClick={() => openTest(p)}><FlaskConical size={13} /> Test</button>
              <button className="btn btn-sm" onClick={() => openEdit(p)}><Pencil size={13} /> Edit</button>
              <button className="btn btn-sm btn-danger" onClick={() => remove(p)}><Trash2 size={13} /> Delete</button>
            </div>
          </div>
        ))}
      </div>

      {editing && (
        <Modal title={editing === 'new' ? 'New REST processor' : 'Edit REST processor'} onClose={() => setEditing(null)}
          footer={<><button className="btn" onClick={() => setEditing(null)}>Cancel</button><button className="btn btn-primary" form="rest-form">Save</button></>}>
          <form id="rest-form" onSubmit={save}>
            <div className="field"><label>Name</label><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></div>
            <div className="field"><label>URL</label><input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} required /></div>
            <div className="form-row-2">
              <div className="field"><label>Method</label>
                <select value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })}>
                  {['POST', 'PUT', 'PATCH', 'GET'].map((m) => <option key={m}>{m}</option>)}
                </select>
              </div>
              <div className="field"><label>Timeout (seconds)</label><input type="number" value={form.timeout} onChange={(e) => setForm({ ...form, timeout: e.target.value })} /></div>
            </div>
            <p className="muted" style={{ marginTop: 12 }}>Headers. Leave a value blank on edit to keep the saved one.</p>
            {form.headers.map((h, i) => (
              <div key={i} className="form-row-2">
                <div className="field"><label>Name</label><input value={h.name} onChange={(e) => setHeader(i, 'name', e.target.value)} placeholder="apikey" /></div>
                <div className="field"><label>Value</label><input type="password" value={h.value} onChange={(e) => setHeader(i, 'value', e.target.value)} placeholder={editing === 'new' ? '' : 'Leave blank to keep'} /></div>
              </div>
            ))}
            <button type="button" className="btn btn-sm" onClick={() => setForm({ ...form, headers: [...form.headers, { name: '', value: '' }] })}>+ Add header</button>
            <label className="field" style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 14 }}>
              <input type="checkbox" checked={form.verify_ssl !== false} onChange={(e) => setForm({ ...form, verify_ssl: e.target.checked })} />
              Verify SSL
            </label>
            <p className="muted">Turn off for an internal certificate.</p>
            <div className="field"><label>Body template</label>
              <textarea rows={6} value={form.body_template} onChange={(e) => setForm({ ...form, body_template: e.target.value })} style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12 }} />
            </div>
            <p className="muted">Jinja over payload. Must render a JSON object.</p>
          </form>
        </Modal>
      )}

      {testing && (
        <Modal title={'Test ' + testing.name} onClose={() => setTesting(null)} footer={<button className="btn" onClick={() => setTesting(null)}>Close</button>}>
          <p className="muted">Does not start a pipeline. Sends the sample as the payload.</p>
          <form onSubmit={runTest}>
            <div className="field"><label>Sample payload</label>
              <textarea rows={6} value={sample} onChange={(e) => setSample(e.target.value)} style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12 }} />
            </div>
            <button className="btn btn-primary" disabled={running} style={{ marginTop: 8 }}>{running ? 'Running…' : 'Run test'}</button>
          </form>
          {result && <pre className="muted" style={{ whiteSpace: 'pre-wrap', marginTop: 12 }}>{JSON.stringify(result.body ?? result, null, 2)}</pre>}
        </Modal>
      )}
    </div>
  )
}
