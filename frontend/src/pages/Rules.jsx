import { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2, ShieldCheck, Pencil, Globe2 } from 'lucide-react'
import api from '../lib/api'
import { useProject, isGlobalResource, visibleLibraryItem } from '../lib/ProjectContext'

export default function Rules() {
  const { projectId, project } = useProject()
  const [items, setItems] = useState([])
  const [error, setError] = useState(null)
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({ name: '', description: '', jdm_json: '' })
  const [saving, setSaving] = useState(false)

  async function load() {
    const { data } = await api.get('/rules')
    setItems(data || [])
  }

  useEffect(() => {
    load().catch((e) => setError(e.message))
  }, [])

  const visible = useMemo(
    () => (items || []).filter((r) => visibleLibraryItem(r, projectId, { includeGlobal: true })),
    [items, projectId],
  )
  const projectOwned = visible.filter((r) => !isGlobalResource(r))
  const globals = visible.filter((r) => isGlobalResource(r))

  async function save(e) {
    e.preventDefault()
    if (!projectId) {
      setError('Select a project before creating a project rule')
      return
    }
    setSaving(true)
    setError(null)
    try {
      let jdm = {}
      try {
        jdm = form.jdm_json.trim() ? JSON.parse(form.jdm_json) : {}
      } catch {
        setError('JDM must be valid JSON')
        setSaving(false)
        return
      }
      const payload = { name: form.name, description: form.description, jdm, project_id: projectId }
      if (modal?.id) {
        // only project-owned editable here
        await api.put(`/rules/${modal.id}`, payload)
      } else {
        await api.post('/rules', payload)
      }
      setModal(null)
      await load()
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setSaving(false)
    }
  }

  async function remove(id) {
    if (!confirm('Delete this project rule?')) return
    await api.delete(`/rules/${id}`)
    await load()
  }

  function Card({ r, global: isGlobal }) {
    return (
      <div
        key={r.id}
        className="org-card"
        style={isGlobal ? {
          borderColor: 'rgba(56, 189, 248, 0.45)',
          background: 'rgba(14, 165, 233, 0.06)',
        } : undefined}
      >
        <div className="org-card-header">
          {isGlobal ? <Globe2 size={18} style={{ color: '#38bdf8' }} /> : <ShieldCheck size={18} />}
          <div>
            <div className="name" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {r.name}
              {isGlobal && <span className="badge badge-blue" style={{ fontSize: 10 }}>Global</span>}
              {!isGlobal && <span className="badge badge-gray" style={{ fontSize: 10 }}>Project</span>}
            </div>
            <div className="url">{r.description || r.id}</div>
          </div>
        </div>
        <div className="org-card-actions">
          {isGlobal ? (
            <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>Read-only · edit in Admin</span>
          ) : (
            <>
              <button className="btn btn-sm" onClick={() => {
                setForm({ name: r.name, description: r.description || '', jdm_json: JSON.stringify(r.jdm || {}, null, 2) })
                setModal({ id: r.id })
              }}><Pencil size={13} /></button>
              <button className="btn btn-sm btn-danger" onClick={() => remove(r.id)}><Trash2 size={13} /></button>
            </>
          )}
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1>Rules</h1>
          <p className="page-sub">
            Project rules plus shared <strong>global</strong> rules (read-only; managed under Admin Configuration).
            {project ? <> Active: <strong>{project.name}</strong></> : null}
          </p>
        </div>
        <button className="btn btn-primary" disabled={!projectId} onClick={() => {
          setForm({ name: '', description: '', jdm_json: '{\n  "nodes": [],\n  "edges": []\n}' })
          setModal({})
        }}>
          <Plus size={15} /> Add project rule
        </button>
      </div>
      {error && <div className="panel" style={{ color: 'var(--accent-red)', marginBottom: 12 }}>{String(error)}</div>}

      <h3 style={{ fontSize: 14, margin: '8px 0 10px', color: 'var(--text-muted)' }}>This project</h3>
      <div className="org-grid" style={{ marginBottom: 20 }}>
        {projectOwned.length === 0 && (
          <div className="panel"><div className="empty-state">No project-specific rules yet.</div></div>
        )}
        {projectOwned.map((r) => <Card key={r.id} r={r} global={false} />)}
      </div>

      <h3 style={{ fontSize: 14, margin: '8px 0 10px', color: 'var(--text-muted)' }}>Global library (read-only)</h3>
      <div className="org-grid">
        {globals.length === 0 && (
          <div className="panel"><div className="empty-state">No global rules. Create them under Admin Configuration.</div></div>
        )}
        {globals.map((r) => <Card key={r.id} r={r} global />)}
      </div>

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-box" style={{ maxWidth: 640 }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header"><h2>{modal.id ? 'Edit project rule' : 'Add project rule'}</h2></div>
            <form onSubmit={save}>
              <div className="modal-body">
                <div className="field"><label>Name</label>
                  <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
                <div className="field"><label>Description</label>
                  <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
                <div className="field"><label>JDM JSON</label>
                  <textarea rows={12} value={form.jdm_json} onChange={(e) => setForm({ ...form, jdm_json: e.target.value })}
                    style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12 }} /></div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setModal(null)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
