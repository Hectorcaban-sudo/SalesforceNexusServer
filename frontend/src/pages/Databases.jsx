import { useEffect, useState } from 'react'
import { Plus, Database, Pencil, Trash2, FlaskConical } from 'lucide-react'
import api from '../lib/api'
import { useToast } from '../lib/ToastContext'

const EMPTY = { name: '', engine: 'postgres', host: '', port: 5432, database: '', username: '', password: '', ssl: false }

function Modal({ title, onClose, children, footer }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()} style={{ width: 640 }}>
        <div className="panel-header"><h3>{title}</h3></div>
        <div className="panel-body">{children}</div>
        <div className="modal-footer">{footer}</div>
      </div>
    </div>
  )
}

export default function Databases() {
  const { toast } = useToast()
  const [rows, setRows] = useState([])
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const fail = (err, fallback) => toast(err?.response?.data?.detail || err?.message || fallback, { kind: 'error' })

  async function load() {
    const { data } = await api.get('/databases')
    setRows(data || [])
  }
  useEffect(() => { load().catch((e) => fail(e, 'Failed to load connections')) }, [])

  function openNew() { setForm(EMPTY); setEditing('new') }
  function openEdit(row) { setForm({ ...EMPTY, ...row, password: '' }); setEditing(row.id) }

  async function save(ev) {
    ev.preventDefault()
    const body = { ...form, port: Number(form.port) }
    try {
      if (editing === 'new') await api.post('/databases', body)
      else await api.put('/databases/' + editing, body)
      toast(editing === 'new' ? 'Connection saved' : 'Connection updated')
      setEditing(null)
      load()
    } catch (err) { fail(err, 'Failed to save connection') }
  }

  async function remove(row) {
    if (!confirm('Delete ' + row.name + '?')) return
    try {
      await api.delete('/databases/' + row.id)
      toast('Connection deleted')
      load()
    } catch (err) { fail(err, 'Delete failed') }
  }

  async function test(row) {
    try {
      await api.post('/databases/' + row.id + '/test')
      toast('Connected')
    } catch (err) { fail(err, 'Connection failed') }
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-end' }}>
        <div>
          <h1>Databases</h1>
          <p className="page-sub">Connections a processor can use. Postgres for now. SQL Server and others can be added later.</p>
        </div>
        <button className="btn btn-primary" onClick={openNew}><Plus size={14} /> New connection</button>
      </div>
      <div className="org-grid">
        {rows.length === 0 && <div className="empty-state">No connections yet</div>}
        {rows.map((row) => (
          <div key={row.id} className="org-card">
            <div className="org-card-header">
              <Database size={16} />
              <div>
                <div className="name">{row.name} <span className="badge badge-blue">{row.engine}</span></div>
                <div className="url">{row.username}@{row.host}:{row.port}/{row.database}</div>
              </div>
            </div>
            <div className="org-card-actions">
              <button className="btn btn-sm" onClick={() => test(row)}><FlaskConical size={13} /> Test</button>
              <button className="btn btn-sm" onClick={() => openEdit(row)}><Pencil size={13} /> Edit</button>
              <button className="btn btn-sm btn-danger" onClick={() => remove(row)}><Trash2 size={13} /> Delete</button>
            </div>
          </div>
        ))}
      </div>
      {editing && (
        <Modal title={editing === 'new' ? 'New connection' : 'Edit connection'} onClose={() => setEditing(null)}
          footer={<><button className="btn" onClick={() => setEditing(null)}>Cancel</button><button className="btn btn-primary" form="db-form">Save</button></>}>
          <form id="db-form" onSubmit={save}>
            <div className="form-row-2">
              <div className="field"><label>Name</label><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></div>
              <div className="field"><label>Engine</label><select value={form.engine} onChange={(e) => setForm({ ...form, engine: e.target.value })}><option value="postgres">Postgres</option></select></div>
              <div className="field"><label>Host</label><input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} required /></div>
              <div className="field"><label>Port</label><input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} /></div>
              <div className="field"><label>Database</label><input value={form.database} onChange={(e) => setForm({ ...form, database: e.target.value })} required /></div>
              <div className="field"><label>Username</label><input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></div>
              <div className="field"><label>Password</label><input type="password" placeholder={editing === 'new' ? '' : 'Leave blank to keep'} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
              <div className="field"><label>SSL</label><select value={form.ssl ? 'yes' : 'no'} onChange={(e) => setForm({ ...form, ssl: e.target.value === 'yes' })}><option value="no">Prefer</option><option value="yes">Require</option></select></div>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
