import { useEffect, useState } from 'react'
import { Plus, Trash2, Code2 } from 'lucide-react'
import api from '../lib/api'

export default function Processors() {
  const [items, setItems] = useState([])
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [name, setName] = useState('')
  const [file, setFile] = useState(null)

  async function load() {
    const { data } = await api.get('/processors')
    setItems(data || [])
  }

  useEffect(() => {
    load().catch((e) => setError(e.message))
  }, [])

  async function upload(e) {
    e.preventDefault()
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('name', name || file.name)
      fd.append('file', file)
      await api.post('/processors', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      setName('')
      setFile(null)
      await load()
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setUploading(false)
    }
  }

  async function remove(id) {
    if (!confirm('Delete this processor?')) return
    await api.delete(`/processors/${id}`)
    await load()
  }

  return (
    <div>
      <div className="page-header">
        <h1>Payload processors</h1>
        <p className="page-sub">Uploaded Python scripts used as custom processing modes on event channels.</p>
      </div>
      {error && <div className="panel" style={{ color: 'var(--accent-red)', marginBottom: 12 }}>{String(error)}</div>}

      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-header"><h3><Plus size={15} /> Upload processor</h3></div>
        <div className="panel-body">
          <form onSubmit={upload}>
            <div className="form-row-2">
              <div className="field">
                <label>Name</label>
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Optional display name" />
              </div>
              <div className="field">
                <label>Python file (.py)</label>
                <input type="file" accept=".py,text/x-python" onChange={(e) => setFile(e.target.files?.[0] || null)} required />
                {file && <div style={{ fontSize: 12, marginTop: 4, color: 'var(--text-muted)' }}>Selected: {file.name}</div>}
              </div>
            </div>
            <button className="btn btn-primary" disabled={uploading || !file} style={{ marginTop: 8 }}>
              {uploading ? 'Uploading…' : 'Upload processor'}
            </button>
          </form>
        </div>
      </div>

      <div className="org-grid">
        {items.length === 0 && <div className="panel"><div className="empty-state">No processors uploaded yet.</div></div>}
        {items.map((p) => (
          <div key={p.id} className="org-card">
            <div className="org-card-header">
              <Code2 size={18} />
              <div>
                <div className="name">{p.name}</div>
                <div className="url">{p.id}</div>
              </div>
            </div>
            <div className="org-card-actions">
              <button className="btn btn-sm btn-danger" onClick={() => remove(p.id)}><Trash2 size={13} /></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
'''
