import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Trash2, Cpu, Globe2, Download, Upload } from 'lucide-react'
import api from '../lib/api'
import PythonHighlight from '../components/PythonHighlight'
import { useProject, isGlobalResource, visibleLibraryItem } from '../lib/ProjectContext'
import { useToast } from '../lib/ToastContext'

export default function Processors() {
  const navigate = useNavigate()
  const { projectId, project } = useProject()
  const { toast } = useToast()
  const replaceRef = useRef(null)
  const [items, setItems] = useState([])
  const [usage, setUsage] = useState({})
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [name, setName] = useState('')
  const [file, setFile] = useState(null)
  const [selected, setSelected] = useState(null)
  const [code, setCode] = useState('')
  const [loadingCode, setLoadingCode] = useState(false)

  async function load() {
    const [{ data }, u] = await Promise.all([
      api.get('/processors', { params: projectId ? { project_id: projectId, include_global: true } : {} }),
      api.get('/processors/usage').catch(() => ({ data: {} })),
    ])
    setItems(data || [])
    setUsage(u.data || {})
  }

  useEffect(() => { load().catch((e) => setError(e.message)) }, [projectId])

  const visible = useMemo(
    () => (items || []).filter((p) => visibleLibraryItem(p, projectId, { includeGlobal: true })),
    [items, projectId],
  )
  const projectOwned = visible.filter((p) => !isGlobalResource(p))
  const globals = visible.filter((p) => isGlobalResource(p))

  async function downloadSample() {
    const { data } = await api.get('/processors/example')
    const blob = new Blob([data.code || ''], { type: 'text/x-python' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'nexus_processor_sample.py'
    a.click()
    URL.revokeObjectURL(a.href)
    toast('Sample downloaded')
  }

  async function upload(e) {
    e.preventDefault()
    if (!file) return
    if (!projectId) {
      toast('Select a project before uploading', { kind: 'error' })
      return
    }
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('name', name || file.name)
      fd.append('file', file)
      fd.append('project_id', projectId)
      await api.post('/processors', fd)
      setName(''); setFile(null)
      toast('Processor uploaded')
      await load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Upload failed', { kind: 'error' })
    } finally { setUploading(false) }
  }

  async function replaceFile(p, fileObj) {
    if (!fileObj) return
    const fd = new FormData()
    fd.append('file', fileObj)
    try {
      await api.post(`/processors/${p.id}/upload`, fd)
      toast(`Replaced ${p.name}`)
      await load()
      if (selected?.id === p.id) openViewer(p)
    } catch (err) {
      toast(err?.response?.data?.detail || 'Replace failed', { kind: 'error' })
    }
  }

  async function remove(id) {
    if (!confirm('Delete this project processor?')) return
    try {
      await api.delete(`/processors/${id}`)
      if (selected?.id === id) setSelected(null)
      toast('Processor deleted')
      await load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Delete failed', { kind: 'error' })
    }
  }

  async function openViewer(p) {
    setSelected(p)
    setLoadingCode(true)
    try {
      const { data } = await api.get(`/processors/${p.id}/code`)
      setCode(data.code || '')
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
      setCode('')
    } finally { setLoadingCode(false) }
  }

  function usedBy(id) { return usage[id] || [] }

  function Card({ p, global: isGlobal }) {
    const hits = usedBy(p.id)
    return (
      <div className="org-card" onClick={() => openViewer(p)} style={{ cursor: 'pointer', outline: selected?.id === p.id ? '1px solid #7eb6d6' : undefined }}>
        <div className="org-card-header">
          {isGlobal ? <Globe2 size={18} /> : <Cpu size={18} />}
          <div>
            <div className="name">{p.name} {isGlobal && <span className="badge badge-blue">Global</span>}</div>
            <div className="url">{hits.length ? `Used by ${hits.length} pipeline${hits.length === 1 ? '' : 's'}` : 'Not used by a pipeline'}</div>
          </div>
        </div>
        <div className="org-card-actions" onClick={(e) => e.stopPropagation()}>
          <button className="btn btn-sm" onClick={() => replaceRef.current && (replaceRef.current.dataset.id = p.id, replaceRef.current.click())}><Upload size={13} /> Replace</button>
          {!isGlobal && <button className="btn btn-sm btn-danger" onClick={() => remove(p.id)}><Trash2 size={13} /></button>}
        </div>
      </div>
    )
  }

  const hits = selected ? usedBy(selected.id) : []

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-end' }}>
        <div>
          <h1>Payload processors</h1>
          <p className="page-sub">Read-only. Replace a script by uploading a .py. {project ? <>Project: <strong>{project.name}</strong></> : null}</p>
        </div>
        <button className="btn btn-sm" onClick={downloadSample}><Download size={13} /> Download sample .py</button>
      </div>
      <input ref={replaceRef} type="file" accept=".py" hidden onChange={(e) => { const id = replaceRef.current?.dataset.id; const f = e.target.files?.[0]; const p = items.find((x) => x.id === id); if (p && f) replaceFile(p, f); e.target.value = '' }} />
      {error && <div className="panel" style={{ color: 'var(--accent-red)', marginBottom: 12 }}>{String(error)}</div>}
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-header"><h3><Plus size={15} /> Upload project processor</h3></div>
        <div className="panel-body">
          <form onSubmit={upload}>
            <div className="form-row-2">
              <div className="field"><label>Name</label><input value={name} onChange={(e) => setName(e.target.value)} /></div>
              <div className="field"><label>Python file (.py)</label><input type="file" accept=".py" onChange={(e) => setFile(e.target.files?.[0] || null)} required /></div>
            </div>
            <button className="btn btn-primary" disabled={uploading || !file || !projectId} style={{ marginTop: 8 }}>{uploading ? 'Uploading…' : 'Upload to this project'}</button>
          </form>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 1fr) minmax(360px, 1.4fr)', gap: 12 }}>
        <div>
          <h3 style={{ fontSize: 13, color: 'var(--text-muted)' }}>This project</h3>
          <div className="org-grid">{projectOwned.map((p) => <Card key={p.id} p={p} />)}{projectOwned.length === 0 && <div className="empty-state">None yet</div>}</div>
          <h3 style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 16 }}>Global library</h3>
          <div className="org-grid">{globals.map((p) => <Card key={p.id} p={p} global />)}</div>
        </div>
        <div className="panel">
          <div className="panel-header">
            <h3>{selected ? `${selected.name}.py` : 'Viewer'} <span className="badge badge-gray">Read only</span></h3>
          </div>
          <div className="panel-body">
            {!selected && <div className="empty-state">Select a processor</div>}
            {selected && loadingCode && <div className="empty-state">Loading…</div>}
            {selected && !loadingCode && <PythonHighlight code={code} readOnly onChange={() => {}} />}
            {selected && (
              <div style={{ marginTop: 12 }}>
                <div className="muted" style={{ marginBottom: 6 }}>Replace by uploading a new .py. Used by:</div>
                {hits.length === 0 && <div className="muted">No pipelines reference this script.</div>}
                {hits.map((h) => (
                  <button key={h.pipeline_id} className="btn btn-sm" style={{ marginRight: 6, marginBottom: 6 }} onClick={() => h.event_id && navigate(`/events/${h.event_id}/pipelines/${h.pipeline_id}/flow`)}>
                    {h.name}{h.event_name ? ` · ${h.event_name}` : ''}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
