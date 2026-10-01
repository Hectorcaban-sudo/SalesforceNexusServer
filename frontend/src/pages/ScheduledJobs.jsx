import { useEffect, useState } from 'react'
import { Plus, Play, Pencil, Trash2 } from 'lucide-react'
import api from '../lib/api'
import { useProject } from '../lib/ProjectContext'
import { useToast } from '../lib/ToastContext'

const EMPTY = {
  name: '', org_id: '', soql: 'SELECT Id, Name FROM Account LIMIT 10',
  cron: '0 2 * * *', timezone: 'America/New_York', mode: 'per_record',
  pipeline_ids: [], enabled: true,
}

export default function ScheduledJobs() {
  const { projectId, project } = useProject()
  const { toast } = useToast()
  const [jobs, setJobs] = useState([])
  const [orgs, setOrgs] = useState([])
  const [pipes, setPipes] = useState([])
  const [form, setForm] = useState(EMPTY)
  const [editId, setEditId] = useState(null)
  const [open, setOpen] = useState(false)
  const [err, setErr] = useState(null)

  async function load() {
    const pid = projectId ? { project_id: projectId } : {}
    const [j, o, p] = await Promise.all([
      api.get('/schedules', { params: pid }),
      api.get('/orgs', { params: pid }),
      api.get('/pipeline-catalog', { params: pid }),
    ])
    setJobs(j.data || [])
    setOrgs(o.data || [])
    setPipes(p.data || [])
  }
  useEffect(() => { load().catch((e) => setErr(e.message)) }, [projectId])

  function openNew() {
    setEditId(null)
    setForm(EMPTY)
    setOpen(true)
  }

  function openEdit(j) {
    setEditId(j.id)
    setForm({
      name: j.name || '',
      org_id: j.org_id || '',
      soql: j.soql || '',
      cron: j.cron || '0 2 * * *',
      timezone: j.timezone || 'UTC',
      mode: j.mode || 'per_record',
      pipeline_ids: j.pipeline_ids || [],
      enabled: j.enabled !== false,
      description: j.description || '',
    })
    setOpen(true)
  }

  async function save(e) {
    e.preventDefault()
    setErr(null)
    const body = { ...form, project_id: projectId || undefined }
    try {
      if (editId) await api.put(`/schedules/${editId}`, body)
      else await api.post('/schedules', body)
      toast(editId ? 'Scheduled job updated' : 'Scheduled job created')
      setOpen(false)
      setEditId(null)
      setForm(EMPTY)
      await load()
    } catch (ex) {
      const detail = ex?.response?.data?.detail || ex.message
      setErr(detail)
      toast(detail || 'Failed to save scheduled job', { kind: 'error' })
    }
  }

  async function toggleEnabled(j) {
    try {
      await api.put(`/schedules/${j.id}`, { enabled: j.enabled === false })
      toast(j.enabled === false ? 'Job enabled' : 'Job disabled')
      await load()
    } catch (ex) {
      toast(ex?.response?.data?.detail || 'Failed to update job', { kind: 'error' })
    }
  }

  async function remove(j) {
    if (!window.confirm(`Delete scheduled job "${j.name}"?`)) return
    try {
      await api.delete(`/schedules/${j.id}`)
      toast('Scheduled job deleted')
      await load()
    } catch (ex) {
      toast(ex?.response?.data?.detail || 'Failed to delete job', { kind: 'error' })
    }
  }

  function togglePipe(id) {
    setForm((f) => ({
      ...f,
      pipeline_ids: f.pipeline_ids.includes(id) ? f.pipeline_ids.filter((x) => x !== id) : [...f.pipeline_ids, id],
    }))
  }

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Scheduled jobs</h1>
          <p>{project ? `${project.name} \u00b7 ` : ''}SOQL on a cron. Same walker as event pipelines.</p>
        </div>
        <button className="btn btn-primary" onClick={openNew}><Plus size={14} /> New job</button>
      </div>
      {err && <div className="panel" style={{ color: 'var(--accent-red)', marginBottom: 12 }}>{String(err)}</div>}
      <div className="panel">
        <table>
          <thead><tr><th>Name</th><th>Org</th><th>Cron</th><th>Pipelines</th><th>Status</th><th>Last run</th><th></th></tr></thead>
          <tbody>
            {jobs.length === 0 && <tr><td colSpan={7} className="empty-state">No scheduled jobs</td></tr>}
            {jobs.map((j) => (
              <tr key={j.id}>
                <td>{j.name}</td>
                <td>{orgs.find((o) => o.id === j.org_id)?.name || j.org_id}</td>
                <td className="mono">{j.cron}</td>
                <td>{(j.pipeline_ids || []).length}</td>
                <td>
                  <button type="button" className="btn btn-sm" onClick={() => toggleEnabled(j)}>
                    {j.enabled === false ? 'Off — enable' : 'On — disable'}
                  </button>
                </td>
                <td>{j.last_error ? <span className="badge badge-red">{j.last_error}</span> : (j.last_count != null ? `${j.last_count} queued` : '—')}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button className="btn btn-sm" onClick={() => openEdit(j)}><Pencil size={12} /> Edit</button>
                  {' '}
                  <button className="btn btn-sm" onClick={() => api.post(`/schedules/${j.id}/run`).then(() => { toast('Job run started'); load() }).catch((ex) => toast(ex?.response?.data?.detail || 'Failed to run job', { kind: 'error' }))}><Play size={12} /> Run</button>
                  {' '}
                  <button className="btn btn-sm btn-danger" onClick={() => remove(j)}><Trash2 size={12} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {open && (
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header"><h3>{editId ? 'Edit scheduled job' : 'New scheduled job'}</h3></div>
            <form onSubmit={save}>
              <div className="panel-body">
                <div className="field"><label>Name</label><input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
                <div className="field">
                  <label>Salesforce org</label>
                  <select required value={form.org_id} onChange={(e) => setForm({ ...form, org_id: e.target.value })}>
                    <option value="">Select…</option>
                    {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                  </select>
                </div>
                <div className="field"><label>SOQL</label><textarea rows={4} className="mono" value={form.soql} onChange={(e) => setForm({ ...form, soql: e.target.value })} /></div>
                <div className="field"><label>Cron (min hour dom mon dow)</label><input value={form.cron} onChange={(e) => setForm({ ...form, cron: e.target.value })} /></div>
                <div className="field">
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input type="checkbox" checked={form.enabled !== false} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
                    Enabled
                  </label>
                </div>
                <div className="field">
                  <label>Target pipelines</label>
                  <button type="button" className="btn btn-sm" style={{ marginBottom: 8 }} onClick={async () => {
                    const name = window.prompt('Standalone pipeline name', 'Scheduled pipeline')
                    if (!name) return
                    const { data } = await api.post('/pipeline-catalog', { name, project_id: projectId || undefined })
                    setPipes((prev) => [...prev, data])
                    setForm((f) => ({ ...f, pipeline_ids: [...f.pipeline_ids, data.id] }))
                  }}>+ Standalone pipeline</button>
                  <div style={{ maxHeight: 180, overflow: 'auto' }}>
                    {pipes.map((p) => (
                      <label key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 6 }}>
                        <input type="checkbox" checked={form.pipeline_ids.includes(p.id)} onChange={() => togglePipe(p.id)} />
                        <span>{p.name}</span>
                        <span className="muted">{p.channel || p.source || 'standalone'}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setOpen(false)}>Cancel</button>
                <button className="btn btn-primary">{editId ? 'Update' : 'Save'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
