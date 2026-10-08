import { useEffect, useState } from 'react'
import { Plus, Database, FlaskConical, Pencil, Trash2 } from 'lucide-react'
import api from '../lib/api'
import { useToast } from '../lib/ToastContext'
import { useProject } from '../lib/ProjectContext'

const EMPTY_PROC = {
  name: '', host: '', port: 9000, ssl: false, collection: '',
  chroma_token: '', cert_id: '', embedding_model_id: '', embed_api_key: '',
  embed_base_url: 'https://devmissionassist.api.us.baesystems.com/{url}/v1',
  embed_header_name: 'apikey', query_template: '{{ payload.User_Message__c }}', n_results: 5,
}

function Modal({ title, onClose, children, footer }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()} style={{ width: 640 }}>
        <div className="panel-header"><h3>{title}</h3></div>
        <div className="panel-body">{children}</div>
        <div className="modal-footer">{footer}</div>
      </div>
    </div>
  )
}

export default function Chroma({ scope = 'global' }) {
  const { toast } = useToast()
  const { project, projectId } = useProject()
  const isProject = scope === 'project'
  const [certs, setCerts] = useState([])
  const [models, setModels] = useState([])
  const [processors, setProcessors] = useState([])
  const [modelForm, setModelForm] = useState({ name: '', url_slug: '', model_id: '', max_tokens: 2048 })
  const [editing, setEditing] = useState(null)
  const [procForm, setProcForm] = useState(EMPTY_PROC)
  const [testing, setTesting] = useState(null)
  const [query, setQuery] = useState('')
  const [n, setN] = useState(5)
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)

  const fail = (err, fallback) => toast(err?.response?.data?.detail || err?.message || fallback, { kind: 'error' })

  async function load() {
    const params = isProject && projectId ? { project_id: projectId } : {}
    const [c, m, p] = await Promise.all([
      api.get('/chroma/certs'),
      api.get('/chroma/models'),
      api.get('/chroma/processors', { params }),
    ])
    setCerts(c.data || [])
    setModels(m.data || [])
    const rows = p.data || []
    setProcessors(isProject ? rows.filter((r) => r.project_id === projectId) : rows.filter((r) => !r.project_id))
  }
  useEffect(() => { load().catch((e) => fail(e, 'Failed to load Chroma settings')) }, [scope, projectId])

  function openNew() {
    setProcForm(EMPTY_PROC)
    setEditing('new')
  }
  function openEdit(p) {
    setProcForm({ ...EMPTY_PROC, ...p, embed_api_key: '', chroma_token: '' })
    setEditing(p.id)
  }
  function openTest(p) {
    setTesting(p)
    setQuery('')
    setN(p.n_results || 5)
    setResult(null)
  }

  async function uploadCert(ev) {
    const file = ev.target.files?.[0]
    if (!file) return
    const body = new FormData()
    body.append('file', file)
    try {
      await api.post('/chroma/certs?name=' + encodeURIComponent(file.name), body)
      toast('Certificate stored')
      load()
    } catch (err) { fail(err, 'Certificate upload failed') }
    ev.target.value = ''
  }

  async function addModel(ev) {
    ev.preventDefault()
    try {
      await api.post('/chroma/models', modelForm)
      toast('Model saved')
      setModelForm({ name: '', url_slug: '', model_id: '', max_tokens: 2048 })
      load()
    } catch (err) { fail(err, 'Failed to save model') }
  }

  async function saveProcessor(ev) {
    ev.preventDefault()
    if (isProject && !projectId && editing === 'new') return fail(new Error('Select a project first'), 'Select a project first')
    const body = {
      ...procForm,
      project_id: isProject ? projectId : null,
      port: Number(procForm.port),
      n_results: Number(procForm.n_results),
    }
    try {
      if (editing === 'new') await api.post('/chroma/processors', body)
      else await api.put('/chroma/processors/' + editing, body)
      toast(editing === 'new' ? 'Processor saved' : 'Processor updated')
      setEditing(null)
      load()
    } catch (err) { fail(err, 'Failed to save processor') }
  }

  async function remove(p) {
    if (!confirm('Delete ' + p.name + '?')) return
    try {
      await api.delete('/chroma/processors/' + p.id)
      toast('Processor deleted')
      load()
    } catch (err) { fail(err, 'Delete failed') }
  }

  async function runQuery(ev) {
    ev.preventDefault()
    setRunning(true)
    try {
      const { data } = await api.post('/chroma/query', { processor_id: testing.id, text: query, n_results: Number(n) })
      setResult(data)
      toast((data.matches || []).length + ' hits')
    } catch (err) { fail(err, 'Query failed') }
    finally { setRunning(false) }
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-end' }}>
        <div>
          <h1>{isProject ? 'Chroma processors' : 'Chroma'}</h1>
          <p className="page-sub">
            {isProject
              ? <>Processors for <strong>{project?.name || 'this project'}</strong>. Certificates and models stay in Administration.</>
              : 'Shared CA certificate, embedding models, and global processors.'}
          </p>
        </div>
        <button className="btn btn-primary" onClick={openNew}><Plus size={14} /> {isProject ? 'New project processor' : 'New global processor'}</button>
      </div>

      {!isProject && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 0.8fr) minmax(360px, 1.2fr)', gap: 12, marginBottom: 16 }}>
          <div className="panel">
            <div className="panel-header"><h3>CA certificates</h3></div>
            <div className="panel-body">
              <p className="muted">One PEM is reused by every processor.</p>
              <label className="btn btn-sm">Upload PEM<input type="file" accept=".pem,.crt" onChange={uploadCert} hidden /></label>
              <div className="org-grid" style={{ marginTop: 12 }}>
                {certs.length === 0 && <div className="empty-state">No certificate yet</div>}
                {certs.map((c) => (
                  <div key={c.id} className="org-card">
                    <div className="org-card-header"><Database size={16} /><div><div className="name">{c.name}</div><div className="url">{c.filename}</div></div></div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="panel">
            <div className="panel-header"><h3>Embedding models</h3></div>
            <div className="panel-body">
              <table className="table">
                <thead><tr><th>Name</th><th>URL slug</th><th>Model</th><th>Max tokens</th></tr></thead>
                <tbody>{models.map((m) => <tr key={m.id}><td>{m.name}</td><td className="muted">{m.url_slug}</td><td className="muted">{m.model_id}</td><td>{m.max_tokens}</td></tr>)}</tbody>
              </table>
              <form onSubmit={addModel} style={{ marginTop: 14 }}>
                <div className="form-row-2">
                  <div className="field"><label>Name</label><input value={modelForm.name} onChange={(e) => setModelForm({ ...modelForm, name: e.target.value })} required /></div>
                  <div className="field"><label>URL slug</label><input value={modelForm.url_slug} onChange={(e) => setModelForm({ ...modelForm, url_slug: e.target.value })} required /></div>
                  <div className="field"><label>Model id</label><input value={modelForm.model_id} onChange={(e) => setModelForm({ ...modelForm, model_id: e.target.value })} /></div>
                  <div className="field"><label>Max tokens</label><input type="number" value={modelForm.max_tokens} onChange={(e) => setModelForm({ ...modelForm, max_tokens: Number(e.target.value) })} /></div>
                </div>
                <button className="btn btn-sm" style={{ marginTop: 8 }}>Add model</button>
              </form>
            </div>
          </div>
        </div>
      )}

      <h3 style={{ fontSize: 13, color: 'var(--text-muted)' }}>{isProject ? 'This project' : 'Global processors'}</h3>
      <div className="org-grid">
        {processors.length === 0 && <div className="empty-state">None yet</div>}
        {processors.map((p) => (
          <div key={p.id} className="org-card">
            <div className="org-card-header">
              <Database size={16} />
              <div>
                <div className="name">{p.name} <span className="badge badge-blue">{isProject ? 'Project' : 'Global'}</span></div>
                <div className="url">{p.collection} · {p.host}:{p.port}</div>
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
        <Modal title={editing === 'new' ? 'New processor' : 'Edit processor'} onClose={() => setEditing(null)}
          footer={<><button className="btn" onClick={() => setEditing(null)}>Cancel</button><button className="btn btn-primary" form="chroma-proc-form">Save</button></>}>
          <form id="chroma-proc-form" onSubmit={saveProcessor}>
            <div className="form-row-2">
              <div className="field"><label>Name</label><input value={procForm.name} onChange={(e) => setProcForm({ ...procForm, name: e.target.value })} required /></div>
              <div className="field"><label>Host</label><input value={procForm.host} onChange={(e) => setProcForm({ ...procForm, host: e.target.value })} required /></div>
              <div className="field"><label>Port</label><input value={procForm.port} onChange={(e) => setProcForm({ ...procForm, port: e.target.value })} /></div>
              <div className="field"><label>Collection</label><input value={procForm.collection} onChange={(e) => setProcForm({ ...procForm, collection: e.target.value })} required /></div>
              <div className="field"><label>CA cert</label><select value={procForm.cert_id || ''} onChange={(e) => setProcForm({ ...procForm, cert_id: e.target.value })}><option value="">None</option>{certs.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
              <div className="field"><label>Embedding model</label><select value={procForm.embedding_model_id || ''} onChange={(e) => setProcForm({ ...procForm, embedding_model_id: e.target.value })}><option value="">Select</option>{models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></div>
              <div className="field"><label>Embed API key</label><input type="password" placeholder={editing === 'new' ? '' : 'Leave blank to keep'} value={procForm.embed_api_key} onChange={(e) => setProcForm({ ...procForm, embed_api_key: e.target.value })} /></div>
              <div className="field"><label>Chroma token</label><input type="password" placeholder={editing === 'new' ? '' : 'Leave blank to keep'} value={procForm.chroma_token} onChange={(e) => setProcForm({ ...procForm, chroma_token: e.target.value })} /></div>
            </div>
            <div className="field" style={{ marginTop: 8 }}><label>Query template</label><input value={procForm.query_template} onChange={(e) => setProcForm({ ...procForm, query_template: e.target.value })} /></div>
          </form>
        </Modal>
      )}

      {testing && (
        <Modal title={'Test ' + testing.name} onClose={() => setTesting(null)} footer={<button className="btn" onClick={() => setTesting(null)}>Close</button>}>
          <p className="muted">Does not start a pipeline. Returns the document and the file metadata.</p>
          <form onSubmit={runQuery}>
            <div className="form-row-2">
              <div className="field"><label>Results</label><input type="number" value={n} onChange={(e) => setN(e.target.value)} /></div>
            </div>
            <div className="field" style={{ marginTop: 8 }}><label>Query</label><textarea value={query} onChange={(e) => setQuery(e.target.value)} rows={3} required /></div>
            <button className="btn btn-primary" disabled={running} style={{ marginTop: 8 }}>{running ? 'Running…' : 'Run test'}</button>
          </form>
          {(result?.matches || []).map((hit) => (
            <div key={hit.id} className="org-card" style={{ marginTop: 10 }}>
              <div className="name">{hit.id} <span className="badge badge-gray">distance {hit.distance}</span></div>
              <p>{hit.document}</p>
              <pre className="muted" style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(hit.metadata, null, 2)}</pre>
            </div>
          ))}
        </Modal>
      )}
    </div>
  )
}
