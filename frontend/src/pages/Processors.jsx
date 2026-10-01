import { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2, Cpu, Globe2, Save, ShieldCheck } from 'lucide-react'
import api from '../lib/api'
import PythonHighlight from '../components/PythonHighlight'
import { useProject, isGlobalResource, visibleLibraryItem } from '../lib/ProjectContext'
import { useToast } from '../lib/ToastContext'

export default function Processors() {
  const { projectId, project } = useProject()
  const { toast } = useToast()
  const [items, setItems] = useState([])
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [name, setName] = useState('')
  const [file, setFile] = useState(null)
  const [selected, setSelected] = useState(null)
  const [code, setCode] = useState('')
  const [syntax, setSyntax] = useState(null)
  const [savingCode, setSavingCode] = useState(false)
  const [loadingCode, setLoadingCode] = useState(false)

  async function load() {
    const { data } = await api.get('/processors', {
      params: projectId ? { project_id: projectId, include_global: true } : {},
    })
    setItems(data || [])
  }

  useEffect(() => { load().catch((e) => setError(e.message)) }, [projectId])

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
      await api.post('/processors', fd)
      setName('')
      setFile(null)
      toast('Processor uploaded')
      await load()
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message
      setError(detail)
      toast(detail || 'Failed to upload processor', { kind: 'error' })
    } finally {
      setUploading(false)
    }
  }

  async function remove(id) {
    if (!confirm('Delete this project processor?')) return
    try {
      await api.delete(`/processors/${id}`)
      toast('Processor deleted')
      await load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Failed to delete processor', { kind: 'error' })
    }
  }

  async function openEditor(p) {
    setSelected(p)
    setLoadingCode(true)
    setSyntax(null)
    try {
      const { data } = await api.get(`/processors/${p.id}/code`)
      setCode(data.code || '')
      if (!(data.code || '').trim()) {
        setError('This processor file is empty on disk. Re-upload the .py or paste the script before saving.')
      }
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
      setCode('')
    } finally {
      setLoadingCode(false)
    }
  }

  async function validateCode() {
    const { data } = await api.post('/processors/validate', { code })
    setSyntax(data)
    return data
  }

  async function saveCode() {
    if (!selected || isGlobalResource(selected) || loadingCode) return
    if (!(code || '').trim()) {
      setError('Cannot save an empty script')
      return
    }
    setSavingCode(true)
    setError(null)
    try {
      const v = await validateCode()
      if (!v.ok) { setError(v.error); toast(v.error || 'Syntax error', { kind: 'error' }); return }
      await api.put(`/processors/${selected.id}/code`, { code })
      toast('Processor saved')
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message
      setError(detail)
      toast(detail || 'Failed to save processor', { kind: 'error' })
    } finally {
      setSavingCode(false)
    }
  }

  function Card({ p, global: isGlobal }) {
    const active = selected?.id === p.id
    return (
      <div key={p.id} className="org-card" onClick={() => openEditor(p)} style={{ cursor: 'pointer', outline: active ? '1px solid var(--accent-blue)' : undefined, ...(isGlobal ? { borderColor: 'rgba(56, 189, 248, 0.45)', background: 'rgba(14, 165, 233, 0.06)' } : {}) }}>
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
            <button className="btn btn-sm btn-danger" onClick={(e) => { e.stopPropagation(); remove(p.id) }}><Trash2 size={13} /></button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1>Payload processors</h1>
        <p className="page-sub">Click a card to view source. Globals are read-only.{project ? <> Active project: <strong>{project.name}</strong></> : null}</p>
      </div>
      {error && <div className="panel" style={{ color: 'var(--accent-red)', marginBottom: 12 }}>{String(error)}</div>}
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-header"><h3><Plus size={15} /> Upload project processor</h3></div>
        <div className="panel-body">
          <form onSubmit={upload}>
            <div className="form-row-2">
              <div className="field"><label>Name</label><input value={name} onChange={(e) => setName(e.target.value)} /></div>
              <div className="field"><label>Python file (.py)</label><input type="file" accept=".py,text/x-python" onChange={(e) => setFile(e.target.files?.[0] || null)} required /></div>
            </div>
            <button className="btn btn-primary" disabled={uploading || !file || !projectId} style={{ marginTop: 8 }}>{uploading ? 'Uploading…' : 'Upload to this project'}</button>
          </form>
        </div>
      </div>
      <h3 style={{ fontSize: 14, margin: '8px 0 10px', color: 'var(--text-muted)' }}>This project</h3>
      <div className="org-grid" style={{ marginBottom: 20 }}>
        {projectOwned.length === 0 && <div className="panel"><div className="empty-state">No project-specific processors yet.</div></div>}
        {projectOwned.map((p) => <Card key={p.id} p={p} global={false} />)}
      </div>
      <h3 style={{ fontSize: 14, margin: '8px 0 10px', color: 'var(--text-muted)' }}>Global library (read-only)</h3>
      <div className="org-grid">
        {globals.length === 0 && <div className="panel"><div className="empty-state">No global processors.</div></div>}
        {globals.map((p) => <Card key={p.id} p={p} global />)}
      </div>
      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div className="modal-box" style={{ maxWidth: 920, width: '92vw' }} onClick={(e) => e.stopPropagation()}>
            <div className="panel-header">
              <h3>{selected.name}.py {isGlobalResource(selected) && <span className="badge badge-blue">Global · read-only</span>}</h3>
              <div style={{ display: 'flex', gap: 8 }}>
                {syntax && <span className={syntax.ok ? 'badge badge-green' : 'badge badge-red'}>{syntax.ok ? 'Syntax OK' : syntax.error}</span>}
                <button type="button" className="btn btn-sm" onClick={validateCode}><ShieldCheck size={13} /> Validate</button>
                <button type="button" className="btn btn-sm btn-primary" disabled={savingCode || loadingCode || isGlobalResource(selected) || !(code || '').trim()} onClick={saveCode}><Save size={13} /> Save</button>
                <button type="button" className="btn btn-sm" onClick={() => setSelected(null)}>Close</button>
              </div>
            </div>
            <div className="panel-body">
              {loadingCode ? <div className="empty-state">Loading…</div> : (
                <PythonHighlight code={code} readOnly={isGlobalResource(selected)} onChange={(v) => { setCode(v); setSyntax(null) }} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
