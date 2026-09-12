import { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2, Pencil, Users, Building2, Zap, MoreHorizontal } from 'lucide-react'
import api from '../lib/api'
import { useProject } from '../lib/ProjectContext'

export default function Projects() {
  const { projects, reload, setProjectId, projectId } = useProject()
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({ name: '', description: '', enabled: true })
  const [members, setMembers] = useState([])
  const [users, setUsers] = useState([])
  const [counts, setCounts] = useState({})
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [menuId, setMenuId] = useState(null)

  useEffect(() => {
    api.get('/users').then((r) => setUsers(r.data || [])).catch(() => {})
  }, [])

  useEffect(() => {
    let cancelled = false
    async function loadCounts() {
      try {
        const [o, e] = await Promise.all([api.get('/orgs'), api.get('/events')])
        if (cancelled) return
        const map = {}
        for (const pr of projects) map[pr.id] = { orgs: 0, events: 0 }
        for (const row of o.data || []) {
          const pid = row.project_id
          if (pid && map[pid]) map[pid].orgs += 1
        }
        for (const row of e.data || []) {
          const pid = row.project_id
          if (pid && map[pid]) map[pid].events += 1
        }
        const def = projects.find((x) => x.name === 'Default Project')
        if (def) {
          map[def.id] = map[def.id] || { orgs: 0, events: 0 }
          for (const row of o.data || []) {
            if (!row.project_id) map[def.id].orgs += 1
          }
          for (const row of e.data || []) {
            if (!row.project_id) map[def.id].events += 1
          }
        }
        setCounts(map)
      } catch {}
    }
    if (projects.length) loadCounts()
    return () => { cancelled = true }
  }, [projects])

  async function openMembers(pr) {
    setError(null)
    try {
      const { data } = await api.get(`/projects/${pr.id}/members`)
      setMembers(data || [])
      setModal({ kind: 'members', project: pr })
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    }
  }

  async function saveProject(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      if (modal?.id) await api.put(`/projects/${modal.id}`, form)
      else await api.post('/projects', form)
      setModal(null)
      await reload()
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setSaving(false)
    }
  }

  async function remove(pr) {
    if (!confirm(`Delete project "${pr.name}"?`)) return
    try {
      await api.delete(`/projects/${pr.id}`)
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

  const sorted = useMemo(
    () => [...projects].sort((a, b) => (a.name || '').localeCompare(b.name || '')),
    [projects],
  )

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
        <div>
          <h1>Projects</h1>
          <p className="page-sub">Manage and organize your Salesforce integration projects.</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => { setForm({ name: '', description: '', enabled: true }); setModal({ kind: 'edit' }) }}
        >
          <Plus size={15} /> Create Project
        </button>
      </div>

      {error && (
        <div className="panel" style={{ color: 'var(--accent-red)', marginBottom: 12 }}>
          {String(error)}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
        {sorted.map((pr) => {
          const c = counts[pr.id] || { orgs: 0, events: 0 }
          const active = projectId === pr.id
          return (
            <div
              key={pr.id}
              className="org-card"
              style={{ position: 'relative', outline: active ? '2px solid var(--accent-blue, #6366f1)' : undefined, cursor: 'pointer' }}
              onClick={() => setProjectId(pr.id)}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div className="name" style={{ fontSize: 16, fontWeight: 600 }}>{pr.name}</div>
                  <div style={{ height: 3, width: 36, borderRadius: 2, background: 'var(--accent-blue, #6366f1)', marginTop: 8 }} />
                </div>
                <button
                  type="button"
                  className="btn btn-sm"
                  style={{ padding: '4px 6px' }}
                  onClick={(e) => { e.stopPropagation(); setMenuId(menuId === pr.id ? null : pr.id) }}
                >
                  <MoreHorizontal size={14} />
                </button>
              </div>

              {menuId === pr.id && (
                <div
                  style={{
                    position: 'absolute', right: 12, top: 44, zIndex: 5,
                    background: 'var(--bg-panel)', border: '1px solid var(--border)',
                    borderRadius: 8, padding: 6, minWidth: 140, boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <button className="btn btn-sm" style={{ width: '100%', justifyContent: 'flex-start', marginBottom: 4 }}
                    onClick={() => { setForm({ name: pr.name, description: pr.description || '', enabled: pr.enabled !== false }); setModal({ kind: 'edit', id: pr.id }); setMenuId(null) }}>
                    <Pencil size={13} /> Edit
                  </button>
                  <button className="btn btn-sm" style={{ width: '100%', justifyContent: 'flex-start', marginBottom: 4 }}
                    onClick={() => { openMembers(pr); setMenuId(null) }}>
                    <Users size={13} /> Admins
                  </button>
                  {pr.name !== 'Default Project' && (
                    <button className="btn btn-sm btn-danger" style={{ width: '100%', justifyContent: 'flex-start' }}
                      onClick={() => { remove(pr); setMenuId(null) }}>
                      <Trash2 size={13} /> Delete
                    </button>
                  )}
                </div>
              )}

              <div style={{ display: 'flex', gap: 24, marginTop: 18 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}>
                  <Building2 size={16} />
                  <div>
                    <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--text)' }}>{c.orgs}</div>
                    <div style={{ fontSize: 11.5 }}>Orgs</div>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}>
                  <Zap size={16} />
                  <div>
                    <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--text)' }}>{c.events}</div>
                    <div style={{ fontSize: 11.5 }}>Events</div>
                  </div>
                </div>
              </div>

              <div style={{ marginTop: 18, paddingTop: 12, borderTop: '1px solid var(--border)', fontSize: 12.5, color: 'var(--text-muted)' }}>
                {pr.description ? <div style={{ marginBottom: 6 }}>{pr.description}</div> : null}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>{active ? 'Active project' : 'Click to switch'}</span>
                  <button type="button" className="btn btn-sm" onClick={(e) => { e.stopPropagation(); openMembers(pr) }}>
                    <Users size={12} /> Admins
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {sorted.length === 0 && (
        <div className="panel"><div className="empty-state">No projects yet. Create one to organize orgs and events.</div></div>
      )}

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
