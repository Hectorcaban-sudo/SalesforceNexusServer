import { useEffect, useState } from 'react'
import { KeyRound, Plus, Trash2 } from 'lucide-react'
import api from '../lib/api'
import { useToast } from '../lib/ToastContext'

export default function ApiClients() {
  const { toast } = useToast()
  const [clients, setClients] = useState([])
  const [projects, setProjects] = useState([])
  const [name, setName] = useState('')
  const [projectId, setProjectId] = useState('')
  const [issued, setIssued] = useState(null)

  async function load() {
    const [c, p] = await Promise.all([
      api.get('/api-clients'),
      api.get('/projects'),
    ])
    setClients(c.data || [])
    setProjects(p.data || [])
  }
  useEffect(() => { load().catch((err) => toast(err?.response?.data?.detail || 'Failed to load clients', { kind: 'error' })) }, [])

  async function createClient(ev) {
    ev.preventDefault()
    try {
      const { data } = await api.post('/api-clients', { name, project_id: projectId || null })
      setIssued(data)
      setName('')
      toast('Client created. Copy the secret now.')
      load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Failed to create client', { kind: 'error' })
    }
  }

  async function toggle(c) {
    try {
      await api.post(`/api-clients/${c.id}/${c.enabled ? 'disable' : 'enable'}`)
      load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Failed to update client', { kind: 'error' })
    }
  }

  async function remove(c) {
    if (!confirm('Delete ' + c.name + '?')) return
    try {
      await api.delete('/api-clients/' + c.id)
      toast('Client deleted')
      load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Delete failed', { kind: 'error' })
    }
  }

  function projectName(id) {
    if (!id) return 'Any project'
    return projects.find((p) => p.id === id)?.name || id
  }

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>API clients</h1>
          <p>Consumer key and secret for POST /api/execute/{'{project}'}/pipeline/{'{pipeline_id}'}. The secret is shown once.</p>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header"><h3><KeyRound size={15} /> New client</h3></div>
        <div className="panel-body">
          <form onSubmit={createClient} className="form-row-2">
            <div className="field"><label>Name</label><input value={name} onChange={(e) => setName(e.target.value)} required placeholder="Contract lookup caller" /></div>
            <div className="field"><label>Project</label>
              <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                <option value="">Any project</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <div><button className="btn btn-primary"><Plus size={13} /> Create client</button></div>
          </form>
          <p className="muted" style={{ marginTop: 10 }}>A client limited to a project can only call pipelines in that project. Any project can call all of them.</p>
          {issued && (
            <div className="panel" style={{ marginTop: 14, padding: 12 }}>
              <p>Copy the secret now. It is not shown again.</p>
              <div className="mono" style={{ marginTop: 8 }}>Key: {issued.consumer_key}</div>
              <div className="mono">Secret: {issued.consumer_secret}</div>
              <p className="muted" style={{ marginTop: 8 }}>Send as X-Consumer-Key and X-Consumer-Secret.</p>
            </div>
          )}
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-header"><h3>Clients</h3></div>
        <table>
          <thead><tr><th>Name</th><th>Consumer key</th><th>Project</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {clients.length === 0 && <tr><td colSpan={5} className="empty-state">No clients yet</td></tr>}
            {clients.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td className="mono">{c.consumer_key}</td>
                <td>{projectName(c.project_id)}</td>
                <td><span className={`badge ${c.enabled ? 'badge-green' : 'badge-gray'}`}>{c.enabled ? 'Enabled' : 'Disabled'}</span></td>
                <td>
                  <button className="btn btn-sm" onClick={() => toggle(c)}>{c.enabled ? 'Disable' : 'Enable'}</button>
                  <button className="btn btn-sm btn-danger" onClick={() => remove(c)}><Trash2 size={13} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
