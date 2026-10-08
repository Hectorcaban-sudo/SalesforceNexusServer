import { useEffect, useState } from 'react'
import api from '../lib/api'
import { useToast } from '../lib/ToastContext'
import { useProject } from '../lib/ProjectContext'

const EMPTY_PROC = {
  name: '', host: '', port: 9000, ssl: false, collection: '',
  chroma_token: '', cert_id: '', embedding_model_id: '', embed_api_key: '',
  embed_base_url: 'https://devmissionassist.api.us.baesystems.com/{url}/v1',
  embed_header_name: 'apikey', query_template: '{{ payload.User_Message__c }}', n_results: 5,
}

export default function Chroma({ scope = 'global' }) {
  const { toast } = useToast()
  const { project, projectId } = useProject()
  const isProject = scope === 'project'
  const [certs, setCerts] = useState([])
  const [models, setModels] = useState([])
  const [processors, setProcessors] = useState([])
  const [processorId, setProcessorId] = useState('')
  const [query, setQuery] = useState('')
  const [n, setN] = useState(5)
  const [result, setResult] = useState(null)
  const [modelForm, setModelForm] = useState({ name: '', url_slug: '', model_id: '', max_tokens: 2048 })
  const [procForm, setProcForm] = useState(EMPTY_PROC)
  const [showForm, setShowForm] = useState(false)

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
    if (!processorId && rows[0]) setProcessorId(rows[0].id)
  }
  useEffect(() => { load().catch((e) => fail(e, 'Failed to load Chroma settings')) }, [scope, projectId])

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

  async function addProcessor(ev) {
    ev.preventDefault()
    if (isProject && !projectId) return fail(new Error('Select a project first'), 'Select a project first')
    const body = {
      ...procForm,
      project_id: isProject ? projectId : null,
      port: Number(procForm.port),
      n_results: Number(procForm.n_results),
    }
    try {
      await api.post('/chroma/processors', body)
      toast(isProject ? 'Project processor saved' : 'Global processor saved')
      setProcForm(EMPTY_PROC)
      setShowForm(false)
      load()
    } catch (err) { fail(err, 'Failed to save processor') }
  }

  async function runQuery(ev) {
    ev.preventDefault()
    try {
      const { data } = await api.post('/chroma/query', { processor_id: processorId, text: query, n_results: Number(n) })
      setResult(data)
      toast((data.matches || []).length + ' hits')
    } catch (err) { fail(err, 'Query failed') }
  }

  const title = isProject ? 'Chroma processors' : 'Chroma'
  const subtitle = isProject
    ? `Processors for ${project?.name || 'the selected project'}. Certs and embedding models stay in Administration.`
    : 'Shared CA certificates, embedding models, and global processors. Project processors are created under the project.'

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>{title}</h1>
          <p className="muted">{subtitle}</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setShowForm((v) => !v)}>
          {isProject ? 'New project processor' : 'New global processor'}
        </button>
      </div>

      {!isProject && (
        <div className="grid-2">
          <section className="panel">
            <div className="panel-header"><h2>CA certificates</h2></div>
            <p className="muted">One PEM is reused by every processor.</p>
            <label className="btn">Upload PEM<input type="file" accept=".pem,.crt" onChange={uploadCert} hidden /></label>
            <table className="data-table">
              <thead><tr><th>Name</th><th>File</th></tr></thead>
              <tbody>
                {certs.length === 0 && <tr><td colSpan={2} className="muted">No certificate yet</td></tr>}
                {certs.map((c) => <tr key={c.id}><td>{c.name}</td><td className="muted">{c.filename}</td></tr>)}
              </tbody>
            </table>
          </section>
          <section className="panel">
            <div className="panel-header"><h2>Embedding models</h2></div>
            <table className="data-table">
              <thead><tr><th>Name</th><th>URL slug</th><th>Model</th><th>Max tokens</th></tr></thead>
              <tbody>{models.map((m) => <tr key={m.id}><td>{m.name}</td><td>{m.url_slug}</td><td>{m.model_id}</td><td>{m.max_tokens}</td></tr>)}</tbody>
            </table>
            <form onSubmit={addModel} className="form-row" style={{ marginTop: 12 }}>
              <input placeholder="Name" value={modelForm.name} onChange={(e) => setModelForm({ ...modelForm, name: e.target.value })} required />
              <input placeholder="URL slug" value={modelForm.url_slug} onChange={(e) => setModelForm({ ...modelForm, url_slug: e.target.value })} required />
              <input placeholder="Model id" value={modelForm.model_id} onChange={(e) => setModelForm({ ...modelForm, model_id: e.target.value })} />
              <input type="number" value={modelForm.max_tokens} onChange={(e) => setModelForm({ ...modelForm, max_tokens: Number(e.target.value) })} />
              <button type="submit" className="btn">Add model</button>
            </form>
          </section>
        </div>
      )}

      <section className="panel">
        <div className="panel-header">
          <h2>{isProject ? 'This project' : 'Global processors'}</h2>
          <span className="badge">{isProject ? 'PROJECT' : 'GLOBAL'}</span>
        </div>
        <table className="data-table">
          <thead><tr><th>Name</th><th>Collection</th><th>Host</th><th>Scope</th></tr></thead>
          <tbody>
            {processors.length === 0 && <tr><td colSpan={4} className="muted">None yet</td></tr>}
            {processors.map((p) => (
              <tr key={p.id}><td>{p.name}</td><td>{p.collection}</td><td>{p.host}:{p.port}</td><td><span className="badge">{p.scope}</span></td></tr>
            ))}
          </tbody>
        </table>
        {showForm && (
          <form onSubmit={addProcessor} className="form-grid" style={{ marginTop: 16 }}>
            <div className="field"><label>Name</label><input value={procForm.name} onChange={(e) => setProcForm({ ...procForm, name: e.target.value })} required /></div>
            <div className="field"><label>Host</label><input value={procForm.host} onChange={(e) => setProcForm({ ...procForm, host: e.target.value })} required /></div>
            <div className="field"><label>Port</label><input value={procForm.port} onChange={(e) => setProcForm({ ...procForm, port: e.target.value })} /></div>
            <div className="field"><label>Collection</label><input value={procForm.collection} onChange={(e) => setProcForm({ ...procForm, collection: e.target.value })} required /></div>
            <div className="field"><label>CA cert</label>
              <select value={procForm.cert_id} onChange={(e) => setProcForm({ ...procForm, cert_id: e.target.value })}>
                <option value="">None</option>
                {certs.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div className="field"><label>Embedding model</label>
              <select value={procForm.embedding_model_id} onChange={(e) => setProcForm({ ...procForm, embedding_model_id: e.target.value })}>
                <option value="">Select</option>
                {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </div>
            <div className="field"><label>Embed API key</label><input type="password" value={procForm.embed_api_key} onChange={(e) => setProcForm({ ...procForm, embed_api_key: e.target.value })} /></div>
            <div className="field"><label>Chroma token</label><input type="password" value={procForm.chroma_token} onChange={(e) => setProcForm({ ...procForm, chroma_token: e.target.value })} /></div>
            <div className="field" style={{ gridColumn: '1 / -1' }}><label>Query template</label><input value={procForm.query_template} onChange={(e) => setProcForm({ ...procForm, query_template: e.target.value })} /></div>
            <button type="submit" className="btn btn-primary">Save</button>
          </form>
        )}
      </section>

      <section className="panel">
        <div className="panel-header"><h2>Test query</h2></div>
        <form onSubmit={runQuery} className="form-grid">
          <div className="field"><label>Processor</label>
            <select value={processorId} onChange={(e) => setProcessorId(e.target.value)}>
              {processors.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div className="field"><label>Results</label><input type="number" value={n} onChange={(e) => setN(e.target.value)} /></div>
          <div className="field" style={{ gridColumn: '1 / -1' }}><label>Query</label><textarea value={query} onChange={(e) => setQuery(e.target.value)} rows={3} required /></div>
          <button type="submit" className="btn btn-primary">Run query</button>
        </form>
        {result && (result.matches || []).map((hit) => (
          <article key={hit.id} className="panel" style={{ marginTop: 12 }}>
            <strong>{hit.id}</strong> <span className="muted">distance {hit.distance}</span>
            <p>{hit.document}</p>
            <pre>{JSON.stringify(hit.metadata, null, 2)}</pre>
          </article>
        ))}
      </section>
    </div>
  )
}
