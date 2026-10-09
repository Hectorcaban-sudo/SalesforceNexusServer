import { useEffect, useState } from 'react'
import api from '../lib/api'
import { useProject } from '../lib/ProjectContext'
import { useToast } from '../lib/ToastContext'

const EMPTY = { name: '', description: '', graphText: '{\n  "nodes": [],\n  "edges": []\n}' }

export default function FlowTemplates() {
  const { projectId } = useProject()
  const { toast } = useToast()
  const [rows, setRows] = useState([])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY)

  function load() {
    const params = projectId ? { project_id: projectId, include_global: true } : {}
    api.get('/flow-templates', { params }).then((r) => setRows(r.data || [])).catch(() => setRows([]))
  }
  useEffect(() => { load() }, [projectId])

  function startNew() {
    setEditing(null)
    setForm(EMPTY)
    setOpen(true)
  }
  function startEdit(row) {
    setEditing(row)
    setForm({
      name: row.name || '',
      description: row.description || '',
      graphText: JSON.stringify(row.graph || { nodes: [], edges: [] }, null, 2),
    })
    setOpen(true)
  }
  async function save() {
    const graph = JSON.parse(form.graphText || '{}')
    const body = { name: form.name, description: form.description, project_id: projectId || null, graph, placeholders: true }
    if (editing) await api.put('/flow-templates/' + editing.id, body)
    else await api.post('/flow-templates', body)
    toast(editing ? 'Template updated' : 'Template created')
    setOpen(false)
    load()
  }
  async function remove(id) {
    await api.delete('/flow-templates/' + id)
    toast('Template deleted')
    load()
  }
  function onFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result || '{}'))
        setForm((f) => ({
          ...f,
          name: f.name || parsed.name || file.name.replace(/\.json$/, ''),
          description: f.description || parsed.description || '',
          graphText: JSON.stringify(parsed.graph || parsed, null, 2),
        }))
      } catch (err) {
        toast(err.message || 'Invalid JSON', { kind: 'error' })
      }
    }
    reader.readAsText(file)
  }

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Templates</h1>
          <p>Saved flows you can apply to a pipeline. Import the NBF JSON or create one here.</p>
        </div>
        <button className="btn btn-primary" onClick={startNew}>New template</button>
      </div>
      <div className="panel">
        <table>
          <thead><tr><th>Name</th><th>Description</th><th>Nodes</th><th></th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={4} className="empty-state">No templates yet</td></tr>}
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td className="muted">{r.description}</td>
                <td>{(r.graph?.nodes || []).length}</td>
                <td>
                  <button className="btn btn-sm" onClick={() => startEdit(r)}>Edit</button>
                  <button className="btn btn-sm" onClick={() => remove(r.id)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {open && (
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header"><h2>{editing ? 'Edit template' : 'New template'}</h2></div>
            <div className="field"><label>Name</label><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
            <div className="field"><label>Description</label><input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
            <div className="field"><label>Import JSON</label><input type="file" accept="application/json" onChange={onFile} /></div>
            <div className="field"><label>Graph</label><textarea rows={10} value={form.graphText} onChange={(e) => setForm({ ...form, graphText: e.target.value })} style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12 }} /></div>
            <div className="modal-actions">
              <button className="btn" onClick={() => setOpen(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={save}>Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
