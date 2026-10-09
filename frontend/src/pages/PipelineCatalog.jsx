import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Workflow } from 'lucide-react'
import api from '../lib/api'
import { useProject } from '../lib/ProjectContext'
import { useToast } from '../lib/ToastContext'

const NBF_GRAPH = {
  nodes: [
    { id: 'source', type: 'source', position: { x: 40, y: 180 }, data: { label: 'ContentDocumentLink', subtitle: 'CREATE' } },
    { id: 'if-create', type: 'if', position: { x: 280, y: 180 }, data: { label: 'Create only', condField: 'ChangeEventHeader.changeType', condOp: 'eq', condValue: 'CREATE' } },
    { id: 'if-user-library', type: 'if', position: { x: 520, y: 180 }, data: { label: 'Skip user library', condField: 'LinkedEntityId', condOp: 'contains', condValue: '005' } },
    { id: 'stop-user', type: 'stop', position: { x: 760, y: 40 }, data: { label: 'Stop', subtitle: 'User library link' } },
    { id: 'get-opportunity', type: 'processor', position: { x: 760, y: 220 }, data: { label: 'Get Opportunity', processingMode: 'flow_action', processorId: '' } },
    { id: 'sharepoint-upload', type: 'processor', position: { x: 1020, y: 220 }, data: { label: 'SharePoint file', processingMode: 'flow_action', processorId: '' } },
    { id: 'if-nbf', type: 'if', position: { x: 1280, y: 220 }, data: { label: 'NBF file only', condField: 'result.sharepoint.file_name', condOp: 'contains', condValue: 'NBF' } },
    { id: 'stop-name', type: 'stop', position: { x: 1520, y: 80 }, data: { label: 'Stop', subtitle: 'Not an NBF file' } },
    { id: 'delete-document', type: 'processor', position: { x: 1520, y: 260 }, data: { label: 'Delete ContentDocument', processingMode: 'flow_action', processorId: '' } },
  ],
  edges: [
    { id: 'e1', source: 'source', target: 'if-create' },
    { id: 'e2', source: 'if-create', target: 'if-user-library', sourceHandle: 'true' },
    { id: 'e3', source: 'if-user-library', target: 'stop-user', sourceHandle: 'true' },
    { id: 'e4', source: 'if-user-library', target: 'get-opportunity', sourceHandle: 'false' },
    { id: 'e5', source: 'get-opportunity', target: 'sharepoint-upload' },
    { id: 'e6', source: 'sharepoint-upload', target: 'if-nbf' },
    { id: 'e7', source: 'if-nbf', target: 'stop-name', sourceHandle: 'false' },
    { id: 'e8', source: 'if-nbf', target: 'delete-document', sourceHandle: 'true' },
  ],
}

export default function PipelineCatalog() {
  const { projectId, project } = useProject()
  const navigate = useNavigate()
  const { toast } = useToast()
  const [rows, setRows] = useState([])
  const [orgFilter, setOrgFilter] = useState('')
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [template, setTemplate] = useState('blank')

  function load() {
    api.get('/pipeline-catalog', { params: projectId ? { project_id: projectId } : {} })
      .then((r) => setRows(r.data || []))
      .catch(() => setRows([]))
  }

  useEffect(() => { load() }, [projectId])

  const orgs = [...new Set(rows.map((r) => r.org_name).filter(Boolean))]
  const visible = useMemo(
    () => rows.filter((r) => !orgFilter || r.org_name === orgFilter),
    [rows, orgFilter],
  )

  async function create() {
    const { data } = await api.post('/pipeline-catalog', {
      name: name || 'Standalone pipeline',
      project_id: projectId || null,
      description: template === 'nbf' ? 'NBF ContentDocument to SharePoint' : 'Standalone pipeline',
      flow_graph: template === 'nbf' ? NBF_GRAPH : { nodes: [], edges: [] },
    })
    toast('Pipeline created')
    navigate(`/pipelines/${data.id}/flow`)
  }

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Pipelines</h1>
          <p>{project ? `${project.name} \u00b7 ` : ''}Event flows and standalone pipelines</p>
        </div>
        <button className="btn btn-primary" onClick={() => setOpen(true)}>New pipeline</button>
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
                <td><span className="badge badge-gray">{p.event_id ? (p.source || 'event') : 'standalone'}</span></td>
                <td>{p.org_name || '\u2014'}</td>
                <td>{p.channel ? <code className="pill">{p.channel}</code> : '\u2014'}</td>
                <td>{p.enabled === false ? 'Off' : 'On'}</td>
                <td>{p.node_count}</td>
                <td>
                  <button className="btn btn-sm btn-primary" onClick={() => navigate(p.event_id ? `/events/${p.event_id}/pipelines/${p.id}/flow` : `/pipelines/${p.id}/flow`)}>
                    <Workflow size={12} /> Open flow
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {open && (
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header"><h2>New pipeline</h2></div>
            <div className="field"><label>Name</label><input value={name} onChange={(e) => setName(e.target.value)} placeholder="NBF ContentDocument" /></div>
            <div className="field">
              <label>Start from</label>
              <select value={template} onChange={(e) => setTemplate(e.target.value)}>
                <option value="blank">Blank</option>
                <option value="nbf">NBF ContentDocument template</option>
              </select>
            </div>
            <p className="muted">This pipeline is not attached to an event. A processor node can call it later.</p>
            <div className="modal-actions">
              <button className="btn" onClick={() => setOpen(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={create}>Create</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
