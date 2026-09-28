import { useEffect, useState } from 'react'
import { Plus, Play } from 'lucide-react'
import api from '../lib/api'
import { useProject } from '../lib/ProjectContext'

const EMPTY = {
  name: '', org_id: '', soql: 'SELECT Id, Name FROM Account LIMIT 10',
  cron: '0 2 * * *', timezone: 'America/New_York', mode: 'per_record',
  pipeline_ids: [], enabled: true,
}

export default function ScheduledJobs() {
  const { projectId, project } = useProject()
  const [jobs, setJobs] = useState([])
  const [orgs, setOrgs] = useState([])
  const [pipes, setPipes] = useState([])
  const [form, setForm] = useState(EMPTY)
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

  async function save(e) {
    e.preventDefault()
    await api.post('/schedules', { ...form, project_id: projectId || undefined })
    setOpen(false)
    setForm(EMPTY)
    load()
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
          <p>{project ? `${project.name} · ` : ''}SOQL on a cron. Same walker as event pipelines.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setOpen(true)}><Plus size={14} /> New job</button>
      </div>
      {err && <div className="panel" style={{ color: 'var(--accent-red)' }}>{err}</div>}
      <div className="panel">
        <table>
          <thead><tr><th>Name</th><th>Org</th><th>Cron</th><th>Pipelines</th><th>Last run</th><th></th></tr></thead>
          <tbody>
            {jobs.length === 0 && <tr><td colSpan={6} className="empty-state">No scheduled jobs</td></tr>}
            {jobs.map((j) => (
              <tr key={j.id}>
                <td>{j.name} {j.enabled === false && <span className="badge badge-gray">off</span>}</td>
                <td>{orgs.find((o) => o.id === j.org_id)?.name || j.org_id}</td>
                <td className="mono">{j.cron}</td>
                <td>{(j.pipeline_ids || []).length}</td>
                <td>{j.last_error ? <span className="badge badge-red">{j.last_error}</span> : (j.last_count != null ? `${j.last_count} queued` : '—')}</td>
                <td><button className="btn btn-sm" onClick={() => api.post(`/schedules/${j.id}/run`).then(load)}><Play size={12} /> Run now</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {open && (
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header"><h3>New scheduled job</h3></div>
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
                  <label>Target pipelines</label>
                  <p className="muted" style={{ fontSize: 12, margin: '0 0 8px' }}>
                    Use an event pipeline, or create a standalone pipeline with no Salesforce subscribe event.
                  </p>
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
                <button className="btn btn-primary">Save</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
