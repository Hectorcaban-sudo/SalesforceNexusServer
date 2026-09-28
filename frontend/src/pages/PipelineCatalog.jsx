import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Workflow } from 'lucide-react'
import api from '../lib/api'
import { useProject } from '../lib/ProjectContext'

export default function PipelineCatalog() {
  const { projectId, project } = useProject()
  const navigate = useNavigate()
  const [rows, setRows] = useState([])
  const [orgFilter, setOrgFilter] = useState('')
<<<<<<< Updated upstream
  useEffect(() => {
    api.get('/pipeline-catalog', { params: projectId ? { project_id: projectId } : {} })
      .then((r) => setRows(r.data || [])).catch(() => setRows([]))
  }, [projectId])
  const orgs = [...new Set(rows.map((r) => r.org_name).filter(Boolean))]
  const visible = useMemo(() => rows.filter((r) => !orgFilter || r.org_name === orgFilter), [rows, orgFilter])
  return (
    <div>
      <div className="page-title-row"><div><h1>Pipelines</h1><p>{project ? `${project.name} \u00b7 ` : ''}All flows in this project</p></div></div>
      <div className="panel">
        <div className="panel-header"><h3>{visible.length} pipeline(s)</h3>
          <select value={orgFilter} onChange={(e) => setOrgFilter(e.target.value)}><option value="">All orgs</option>{orgs.map((o) => <option key={o} value={o}>{o}</option>)}</select>
        </div>
        <table><thead><tr><th>Name</th><th>Source</th><th>Org</th><th>Channel</th><th>Enabled</th><th>Nodes</th><th></th></tr></thead>
        <tbody>
          {visible.length === 0 && <tr><td colSpan={7} className="empty-state">No pipelines yet</td></tr>}
          {visible.map((p) => (
            <tr key={p.id}>
              <td>{p.name}</td><td><span className="badge badge-gray">{p.source || 'event'}</span></td>
              <td>{p.org_name}</td><td><code className="pill">{p.channel}</code></td>
              <td>{p.enabled === false ? 'Off' : 'On'}</td><td>{p.node_count}</td>
              <td><button className="btn btn-sm btn-primary" onClick={() => navigate(`/events/${p.event_id}/pipelines/${p.id}/flow`)}><Workflow size={12} /> Open flow</button></td>
            </tr>
          ))}
        </tbody></table>
=======

  useEffect(() => {
    api.get('/pipeline-catalog', { params: projectId ? { project_id: projectId } : {} })
      .then((r) => setRows(r.data || []))
      .catch(() => setRows([]))
  }, [projectId])

  const orgs = [...new Set(rows.map((r) => r.org_name).filter(Boolean))]
  const visible = useMemo(
    () => rows.filter((r) => !orgFilter || r.org_name === orgFilter),
    [rows, orgFilter],
  )

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Pipelines</h1>
          <p>{project ? `${project.name} · ` : ''}All flows in this project</p>
        </div>
      </div>
      <div className="panel">
        <div className="panel-header">
          <h3>{visible.length} pipeline(s)</h3>
          <select value={orgFilter} onChange={(e) => setOrgFilter(e.target.value)}>
            <option value="">All orgs</option>
            {orgs.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
        <table>
          <thead>
            <tr><th>Name</th><th>Source</th><th>Org</th><th>Channel</th><th>Enabled</th><th>Nodes</th><th></th></tr>
          </thead>
          <tbody>
            {visible.length === 0 && <tr><td colSpan={7} className="empty-state">No pipelines yet</td></tr>}
            {visible.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td><span className="badge badge-gray">{p.source || 'event'}</span></td>
                <td>{p.org_name}</td>
                <td><code className="pill">{p.channel}</code></td>
                <td>{p.enabled === false ? 'Off' : 'On'}</td>
                <td>{p.node_count}</td>
                <td>
                  <button className="btn btn-sm btn-primary" onClick={() => navigate(`/events/${p.event_id}/pipelines/${p.id}/flow`)}>
                    <Workflow size={12} /> Open flow
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
>>>>>>> Stashed changes
      </div>
    </div>
  )
}
