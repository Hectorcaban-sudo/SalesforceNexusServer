import { useEffect, useState } from 'react'
import { Plus, FolderKanban, Trash2, Pencil, Users } from 'lucide-react'
import api from '../lib/api'
import { useProject } from '../lib/ProjectContext'

export default function Projects() {
  const { projects, reload, setProjectId, projectId } = useProject()
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({ name: '', description: '', enabled: true })
  const [members, setMembers] = useState([])
  const [users, setUsers] = useState([])
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get('/users').then((r) => setUsers(r.data || [])).catch(() => {})
  }, [])

  async function openMembers(p) {
    setError(null)
    try {
      const { data } = await api.get(`/projects/${p.id}/members`)
      setMembers(data || [])
      setModal({ kind: 'members', project: p })
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    }
  }

  async function saveProject(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      if (modal?.id) {
        await api.put(`/projects/${modal.id}`, form)
      } else {
        await api.post('/projects', form)
      }
      setModal(null)
      await reload()
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setSaving(false)
    }
  }

  async function remove(p) {
    if (!confirm(`Delete project "${p.name}"?`)) return
    try {
      await api.delete(`/projects/${p.id}`)
      await reload()
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    }
  }

  async function addMember(userId) {
    if (!modal?.project) return
    try {
      await api.post(`/projects/${modal.project.id}/members`, { user_id: userId, role: 'project_admin' })
      const { data } = await api.get(`/projects/${modal.project.id}/members`)
      setMembers(data || [])
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    }
  }

  async function removeMember(memberId) {
    if (!modal?.project) return
    await api.delete(`/projects/${modal.project.id}/members/${memberId}`)
    const { data } = await api.get(`/projects/${modal.project.id}/members`)
    setMembers(data || [])
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1>Projects</h1>
          <p className="page-sub">Organize Salesforce customers and solutions. Active project filters orgs, events, and integrations.</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => { setForm({ name: '', description: '', enabled: true }); setModal({ kind: 'edit' }) }}
        >
          <Plus size={15} /> Create project
        </button>
      </div>

      {error && <div className="panel" style={{ color: 'var(--accent-red)', marginBottom: 12 }}>{String(error)}</div>}

      <div className="org-grid">
        {projects.map((p) => (
          <div key={p.id} className={`org-card ${projectId === p.id ? 'selected' : ''}`} style={projectId === p.id ? { outline: '2px solid var(--accent-blue, #6366f1)' } : undefined}>
            <div className="org-card-header">
              <FolderKanban size={18} />
              <div>
                <div className="name">{p.name}</div>
                <div className="url">{p.description || 'No description'}</div>
              </div>
            </div>
            <div className="org-card-actions">
              <button className="btn btn-sm" onClick={() => setProjectId(p.id)}>
                {projectId === p.id ? 'Active' : 'Switch'}
              </button>
              <button className="btn btn-sm" onClick={() => openMembers(p)}><Users size={13} /> Admins</button>
              <button className="btn btn-sm" onClick={() => { setForm({ name: p.name, description: p.description || '', enabled: p.enabled !== false }); setModal({ kind: 'edit', id: p.id }) }}>
                <Pencil size={13} />
              </button>
              {p.name !== 'Default Project' && (
                <button className="btn btn-sm btn-danger" onClick={() => remove(p)}><Trash2 size={13} /></button>
              )}
            </div>
          </div>
        ))}
      </div>

      {modal?.kind === 'edit' && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header"><h2>{modal.id ? 'Edit project' : 'Create project'}</h2></div>
            <form onSubmit={saveProject}>
              <div className="modal-body">
                <div className="field"><label>Name</label>
                  <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
                <div className="field"><label>Description</label>
                  <textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setModal(null)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {modal?.kind === 'members' && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header"><h2>Project admins — {modal.project.name}</h2></div>
            <div className="modal-body">
              <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 12px' }}>
                {members.map((m) => (
                  <li key={m.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                    <span>{m.username || m.user_id} <span className="badge badge-gray">{m.role}</span></span>
                    <button type="button" className="btn btn-sm btn-danger" onClick={() => removeMember(m.id)}>Remove</button>
                  </li>
                ))}
                {members.length === 0 && <li className="empty-state">No project admins assigned</li>}
              </ul>
              <div className="field">
                <label>Add user as project admin</label>
                <select defaultValue="" onChange={(e) => { if (e.target.value) addMember(e.target.value); e.target.value = '' }}>
                  <option value="">Select user…</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>{u.username} ({u.role})</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="modal-footer">
              <button type="button" className="btn" onClick={() => setModal(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
'''
