import { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2, Cpu, Globe2 } from 'lucide-react'
import api from '../lib/api'
import { useProject, isGlobalResource, visibleLibraryItem } from '../lib/ProjectContext'

export default function Processors() {
  const { projectId, project } = useProject()
  const [items, setItems] = useState([])
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [name, setName] = useState('')
  const [file, setFile] = useState(null)

  async function load() {
    const { data } = await api.get('/processors', {
      params: projectId ? { project_id: projectId, include_global: true } : {},
    })
    setItems(data || [])
  }

  useEffect(() => {
    load().catch((e) => setError(e.message))
  }, [projectId])

  const visible = useMemo(
    () => (items || []).filter((p) => visibleLibraryItem(p, projectId, { includeGlobal: true })),
    [items, projectId],
  )
  const projectOwned = visible.filter((p) => !isGlobalResource(p))
  const globals = visible.filter((p) => isGlobalResource(p))

  async function upload(e) {
    e.preventDefault()
    if (!file) return
    if (!projectId) {
      setError('Select a project in the top bar before uploading a project processor')
      return
    }
    setUploading(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('name', name || file.name)
      fd.append('file', file)
      fd.append('project_id', projectId)
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
    if (!confirm('Delete this project processor?')) return
    await api.delete(`/processors/${id}`)
    await load()
  }

  function Card({ p, global: isGlobal }) {
    return (
      <div
        key={p.id}
        className="org-card"
        style={isGlobal ? {
          borderColor: 'rgba(56, 189, 248, 0.45)',
          background: 'rgba(14, 165, 233, 0.06)',
        } : undefined}
      >
        <div className="org-card-header">
          {isGlobal ? <Globe2 size={18} style={{ color: '#38bdf8' }} /> : <Cpu size={18} />}
          <div>
            <div className="name" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {p.name}
              {isGlobal && <span className="badge badge-blue" style={{ fontSize: 10 }}>Global</span>}
              {!isGlobal && <span className="badge badge-gray" style={{ fontSize: 10 }}>Project</span>}
            </div>
            <div className="url">{p.id}</div>
          </div>
        </div>
        <div className="org-card-actions">
          {isGlobal ? (
            <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>Read-only · edit in Admin</span>
          ) : (
            <button className="btn btn-sm btn-danger" onClick={() => remove(p.id)}><Trash2 size={13} /></button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1>Payload processors</h1>
        <p className="page-sub">
          Project processors you can upload here, plus shared <strong>global</strong> processors (read-only; managed under Administration → Admin Configuration).
          {project ? <> Active project: <strong>{project.name}</strong></> : null}
        </p>
      </div>
      {error && <div className="panel" style={{ color: 'var(--accent-red)', marginBottom: 12 }}>{String(error)}</div>}

      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-header"><h3><Plus size={15} /> Upload project processor</h3></div>
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
            <button className="btn btn-primary" disabled={uploading || !file || !projectId} style={{ marginTop: 8 }}>
              {uploading ? 'Uploading…' : 'Upload to this project'}
            </button>
          </form>
        </div>
      </div>

      <h3 style={{ fontSize: 14, margin: '8px 0 10px', color: 'var(--text-muted)' }}>This project</h3>
      <div className="org-grid" style={{ marginBottom: 20 }}>
        {projectOwned.length === 0 && (
          <div className="panel"><div className="empty-state">No project-specific processors yet.</div></div>
        )}
        {projectOwned.map((p) => <Card key={p.id} p={p} global={false} />)}
      </div>

      <h3 style={{ fontSize: 14, margin: '8px 0 10px', color: 'var(--text-muted)' }}>Global library (read-only)</h3>
      <div className="org-grid">
        {globals.length === 0 && (
          <div className="panel"><div className="empty-state">No global processors. Create them under Admin Configuration.</div></div>
        )}
        {globals.map((p) => <Card key={p.id} p={p} global />)}
      </div>
    </div>
  )
}
