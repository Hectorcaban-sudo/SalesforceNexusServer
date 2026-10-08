import { useEffect, useState } from 'react'
import api from '../lib/api'
import { useToast } from '../lib/ToastContext'

export default function Chroma() {
  const { toast } = useToast()
  const [certs, setCerts] = useState([])
  const [models, setModels] = useState([])
  const [processors, setProcessors] = useState([])
  const [processorId, setProcessorId] = useState('')
  const [query, setQuery] = useState('')
  const [n, setN] = useState(5)
  const [result, setResult] = useState(null)
  const [modelForm, setModelForm] = useState({ name: '', url_slug: '', model_id: '', max_tokens: 2048 })
  const [procForm, setProcForm] = useState({
    name: '', project_id: '', host: '', port: 9000, ssl: false, collection: '',
    chroma_token: '', cert_id: '', embedding_model_id: '', embed_api_key: '',
    embed_base_url: 'https://devmissionassist.api.us.baesystems.com/{url}/v1',
    embed_header_name: 'apikey', query_template: '{{ payload.User_Message__c }}', n_results: 5,
  })

  async function load() {
    const [c, m, p] = await Promise.all([
      api.get('/chroma/certs'), api.get('/chroma/models'), api.get('/chroma/processors'),
    ])
    setCerts(c.data || [])
    setModels(m.data || [])
    setProcessors(p.data || [])
    if (!processorId && (p.data || [])[0]) setProcessorId(p.data[0].id)
  }
  const fail = (err, fallback) => toast(err?.response?.data?.detail || err?.message || fallback, { kind: 'error' })
  useEffect(() => { load().catch((e) => fail(e, 'Failed to load Chroma settings')) }, [])

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
    const body = { ...procForm, project_id: procForm.project_id || null, port: Number(procForm.port), n_results: Number(procForm.n_results) }
    try {
      await api.post('/chroma/processors', body)
      toast('Chroma processor saved')
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

  return (
    <div className="page">
      <h1>Chroma</h1>
      <p className="muted">Upload a CA cert, keep the embedding model list, save a Chroma processor, then pick processing mode Chroma on a flow's Processor node (or as the global mode in Admin Configuration). Query here to see document text and file metadata.</p>

      <section className="panel">
        <h2>CA certificates</h2>
        <input type="file" accept=".pem,.crt" onChange={uploadCert} />
        <ul>{certs.map((c) => <li key={c.id}>{c.name} <span className="muted">{c.filename}</span></li>)}</ul>
      </section>

      <section className="panel">
        <h2>Embedding models</h2>
        <table className="data-table"><thead><tr><th>Name</th><th>URL slug</th><th>Model</th><th>Max tokens</th></tr></thead>
          <tbody>{models.map((m) => <tr key={m.id}><td>{m.name}</td><td>{m.url_slug}</td><td>{m.model_id}</td><td>{m.max_tokens}</td></tr>)}</tbody></table>
        <form onSubmit={addModel} className="form-grid">
          <input placeholder="Name" value={modelForm.name} onChange={(e) => setModelForm({ ...modelForm, name: e.target.value })} required />
          <input placeholder="URL slug" value={modelForm.url_slug} onChange={(e) => setModelForm({ ...modelForm, url_slug: e.target.value })} required />
          <input placeholder="Model id" value={modelForm.model_id} onChange={(e) => setModelForm({ ...modelForm, model_id: e.target.value })} />
          <input type="number" value={modelForm.max_tokens} onChange={(e) => setModelForm({ ...modelForm, max_tokens: Number(e.target.value) })} />
          <button type="submit">Add model</button>
        </form>
      </section>

      <section className="panel">
        <h2>Processors</h2>
        <p className="muted">Empty project id = global. Select it from the Processor node (mode Chroma) in the flow designer, or as the global processing mode.</p>
        <ul>{processors.map((p) => <li key={p.id}><strong>{p.name}</strong> <span className="badge">{p.scope}</span> {p.collection}</li>)}</ul>
        <form onSubmit={addProcessor} className="form-grid">
          <input placeholder="Name" value={procForm.name} onChange={(e) => setProcForm({ ...procForm, name: e.target.value })} required />
          <input placeholder="Project id (blank = global)" value={procForm.project_id} onChange={(e) => setProcForm({ ...procForm, project_id: e.target.value })} />
          <input placeholder="Chroma host" value={procForm.host} onChange={(e) => setProcForm({ ...procForm, host: e.target.value })} required />
          <input placeholder="Port" value={procForm.port} onChange={(e) => setProcForm({ ...procForm, port: e.target.value })} />
          <input placeholder="Collection" value={procForm.collection} onChange={(e) => setProcForm({ ...procForm, collection: e.target.value })} required />
          <input placeholder="Chroma token" type="password" value={procForm.chroma_token} onChange={(e) => setProcForm({ ...procForm, chroma_token: e.target.value })} />
          <select value={procForm.cert_id} onChange={(e) => setProcForm({ ...procForm, cert_id: e.target.value })}>
            <option value="">CA cert</option>
            {certs.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select value={procForm.embedding_model_id} onChange={(e) => setProcForm({ ...procForm, embedding_model_id: e.target.value })}>
            <option value="">Embedding model</option>
            {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
          <input placeholder="Embed API key" type="password" value={procForm.embed_api_key} onChange={(e) => setProcForm({ ...procForm, embed_api_key: e.target.value })} />
          <button type="submit">Save processor</button>
        </form>
      </section>

      <section className="panel">
        <h2>Query</h2>
        <form onSubmit={runQuery}>
          <select value={processorId} onChange={(e) => setProcessorId(e.target.value)}>
            {processors.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <textarea value={query} onChange={(e) => setQuery(e.target.value)} rows={4} placeholder="Query text" required />
          <input type="number" value={n} onChange={(e) => setN(e.target.value)} />
          <button type="submit">Run query</button>
        </form>
        {result && (
          <div>
            <p>Collection metadata: {JSON.stringify(result.collection_metadata || {})}</p>
            {(result.matches || []).map((hit) => (
              <article key={hit.id} className="panel">
                <strong>{hit.id}</strong> <span className="muted">distance {hit.distance}</span>
                <p>{hit.document}</p>
                <pre>{JSON.stringify(hit.metadata, null, 2)}</pre>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
