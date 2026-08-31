import { useEffect, useState } from 'react'
import { Plus, Trash2, KeyRound, UserCog } from 'lucide-react'
import api from '../lib/api'
import { useAuth } from '../lib/AuthContext'

const EMPTY = { username: '', password: '', role: 'viewer' }

export default function Users() {
  const { user: currentUser } = useAuth()
  const [users, setUsers] = useState([])
  const [modalOpen, setModalOpen] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const [resetTarget, setResetTarget] = useState(null)
  const [resetPassword, setResetPassword] = useState('')

  async function load() {
    const { data } = await api.get('/users')
    setUsers(data)
  }

  useEffect(() => { load() }, [])

  async function createUser(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await api.post('/users', form)
      setModalOpen(false)
      setForm(EMPTY)
      load()
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to create user')
    } finally {
      setSaving(false)
    }
  }

  async function changeRole(username, role) {
    await api.put(`/users/${username}`, { role })
    load()
  }

  async function removeUser(username) {
    if (!confirm(`Delete user "${username}"?`)) return
    await api.delete(`/users/${username}`)
    load()
  }

  async function submitReset(e) {
    e.preventDefault()
    await api.put(`/users/${resetTarget}`, { password: resetPassword })
    setResetTarget(null)
    setResetPassword('')
  }

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Users</h1>
          <p>Manage admin console accounts and their roles — admin, operator, or viewer</p>
        </div>
        <button className="btn btn-primary" onClick={() => setModalOpen(true)}><Plus size={15} /> Add user</button>
      </div>

      <div className="panel">
        <table>
          <thead><tr><th>Username</th><th>Role</th><th>Auth</th><th>Created</th><th></th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.username}>
                <td>{u.username}{u.username === currentUser?.username && <span style={{ color: 'var(--text-muted)', fontSize: 11 }}> (you)</span>}</td>
                <td>
                  <select
                    value={u.role}
                    onChange={(e) => changeRole(u.username, e.target.value)}
                    style={{ width: 130 }}
                    disabled={u.username === currentUser?.username}
                  >
                    <option value="viewer">Viewer</option>
                    <option value="operator">Operator</option>
                    <option value="admin">Admin</option>
                  </select>
                </td>
                <td><span className="badge badge-gray">{u.auth_provider}</span></td>
                <td className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  {u.created_at ? new Date(u.created_at * 1000).toLocaleDateString() : '—'}
                </td>
                <td style={{ display: 'flex', gap: 6 }}>
                  {u.auth_provider === 'local' && (
                    <button className="btn btn-sm btn-icon" title="Reset password" onClick={() => setResetTarget(u.username)}>
                      <KeyRound size={13} />
                    </button>
                  )}
                  <button
                    className="btn btn-sm btn-icon btn-danger"
                    disabled={u.username === currentUser?.username}
                    onClick={() => removeUser(u.username)}
                  >
                    <Trash2 size={13} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modalOpen && (
        <div className="modal-overlay" onClick={() => setModalOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header"><h3><UserCog size={15} /> Add user</h3></div>
            <form onSubmit={createUser}>
              <div className="panel-body">
                <div className="field">
                  <label>Username</label>
                  <input required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
                </div>
                <div className="field">
                  <label>Password</label>
                  <input required type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
                </div>
                <div className="field">
                  <label>Role</label>
                  <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                    <option value="viewer">Viewer — read-only dashboard, transactions, logs</option>
                    <option value="operator">Operator — can manage orgs/events, reprocess transactions</option>
                    <option value="admin">Admin — full access including users and integrations</option>
                  </select>
                </div>
                {error && <div style={{ color: 'var(--accent-red)', fontSize: 12.5 }}>{error}</div>}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Creating…' : 'Create user'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {resetTarget && (
        <div className="modal-overlay" onClick={() => setResetTarget(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header"><h3><KeyRound size={15} /> Reset password for {resetTarget}</h3></div>
            <form onSubmit={submitReset}>
              <div className="panel-body">
                <div className="field">
                  <label>New password</label>
                  <input required type="password" value={resetPassword} onChange={(e) => setResetPassword(e.target.value)} autoFocus />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setResetTarget(null)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Reset password</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
