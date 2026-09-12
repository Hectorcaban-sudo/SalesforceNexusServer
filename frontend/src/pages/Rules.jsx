import { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2, ShieldCheck, Pencil } from 'lucide-react'
import api from '../lib/api'
import { useProject, belongsToProject } from '../lib/ProjectContext'

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

  async function save(e) {
    e.preventDefault()
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
      const payload = { name: form.name, description: form.description, jdm }
      if (modal?.id) await api.put(`/rules/${modal.id}`, payload)
      else await api.post('/rules', payload)
      setModal(null)
      await load()
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setSaving(false)
    }
  }

  async function remove(id) {
    if (!confirm('Delete this rule?')) return
    await api.delete(`/rules/${id}`)
    await load()
  }

  const visible = useMemo(
    () => (items || []).filter((r) => belongsToProject(r, projectId, project)),
    [items, projectId, project],
  )

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1>Rules</h1>
          <p className="page-sub">GoRules / Zen decision graphs used as choice gates on event flows.</p>
        </div>
        <button className="btn btn-primary" onClick={() => { setForm({ name: '', description: '', jdm_json: '{\n  "nodes": [],\n  "edges": []\n}' }); setModal({}) }}>
          <Plus size={15} /> Add rule
        </button>
      </div>
      {error && <div className="panel" style={{ color: 'var(--accent-red)', marginBottom: 12 }}>{String(error)}</div>}

      <div className="org-grid">
        {visible.length === 0 && <div className="panel"><div className="empty-state">No rules yet. Create one or import JDM from Admin Configuration.</div></div>}
        {visible.map((r) => (
          <div key={r.id} className="org-card">
            <div className="org-card-header">
              <ShieldCheck size={18} />
              <div>
                <div className="name">{r.name}</div>
                <div className="url">{r.description || r.id}</div>
              </div>
            </div>
            <div className="org-card-actions">
              <button className="btn btn-sm" onClick={() => {
                setForm({ name: r.name, description: r.description || '', jdm_json: JSON.stringify(r.jdm || r.decision_graph || {}, null, 2) })
                setModal({ id: r.id })
              }}>
                <Pencil size={13} />
              </button>
              <button className="btn btn-sm btn-danger" onClick={() => remove(r.id)}><Trash2 size={13} /></button>
            </div>
          </div>
        ))}
      </div>

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-box" style={{ maxWidth: 640 }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header"><h2>{modal.id ? 'Edit rule' : 'Add rule'}</h2></div>
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
