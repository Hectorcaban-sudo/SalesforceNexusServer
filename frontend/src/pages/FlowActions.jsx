import { useEffect, useState } from 'react'
import api from '../lib/api'
import { useProject } from '../lib/ProjectContext'
import { useToast } from '../lib/ToastContext'

const EMPTY = {
  name: '',
  type: 'sharepoint_file',
  object_template: 'ContentDocument',
  id_template: '{{ payload.ContentDocumentId }}',
  sharepoint_action_id: '',
  chroma_processor_id: '',
  replace_existing: true,
  name_prefix: '',
}

function detail(row) {
  if (row.type === 'sharepoint_file') return row.replace_existing ? 'Replace existing' : 'Upload'
  if (row.type === 'chroma') return 'Returns document and metadata'
  return row.object_template
}

export default function FlowActions() {
  const { projectId } = useProject()
  const { toast } = useToast()
  const [rows, setRows] = useState([])
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [spActions, setSpActions] = useState([])
  const [chromaProcessors, setChromaProcessors] = useState([])

  async function load() {
    const { data } = await api.get('/flow-actions')
    const all = data || []
    setRows(projectId ? all.filter((r) => !r.project_id || r.project_id === projectId) : all)
  }

  useEffect(() => { load().catch((e) => toast(e.message || 'Could not load flow actions')) }, [projectId])
  useEffect(() => {
    api.get('/sharepoint/file-actions').then((r) => setSpActions(r.data || [])).catch(() => setSpActions([]))
    api.get('/chroma/processors').then((r) => setChromaProcessors(r.data || [])).catch(() => setChromaProcessors([]))
  }, [])

  function set(key, value) { setForm((f) => ({ ...f, [key]: value })) }

  async function save() {
    await api.post('/flow-actions', { ...form, project_id: projectId || null })
    setOpen(false)
    setForm(EMPTY)
    toast('Flow action saved')
    load()
  }

  async function remove(id) {
    await api.delete('/flow-actions/' + id)
    toast('Flow action deleted')
    load()
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Flow actions</h1>
          <p className="muted">Reusable steps any pipeline can call. A Chroma action returns the hits to the next node.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setOpen(true)}>New action</button>
      </div>
      <div className="panel">
        <table className="data-table">
          <thead><tr><th>Name</th><th>Type</th><th>Detail</th><th></th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td><span className="badge">{r.type}</span></td>
                <td className="muted">{detail(r)}</td>
                <td><button className="btn btn-ghost" onClick={() => remove(r.id)}>Delete</button></td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={4} className="empty-state">No flow actions yet</td></tr>}
          </tbody>
        </table>
      </div>
      {open && (
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header"><h2>New flow action</h2></div>
            <div className="field"><label>Name</label><input value={form.name} onChange={(e) => set('name', e.target.value)} /></div>
            <div className="field">
              <label>Type</label>
              <select value={form.type} onChange={(e) => set('type', e.target.value)}>
                <option value="salesforce_get">Salesforce get</option>
                <option value="salesforce_delete">Salesforce delete</option>
                <option value="sharepoint_file">SharePoint file</option>
                <option value="chroma">Chroma</option>
              </select>
            </div>
            {form.type === 'sharepoint_file' && (
              <>
                <div className="field">
                  <label>SharePoint action</label>
                  <select value={form.sharepoint_action_id} onChange={(e) => set('sharepoint_action_id', e.target.value)}>
                    <option value="">Select action</option>
                    {spActions.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                  </select>
                </div>
                <label className="check-row"><input type="checkbox" checked={form.replace_existing} onChange={(e) => set('replace_existing', e.target.checked)} /> Replace existing file</label>
              </>
            )}
            {form.type === 'chroma' && (
              <div className="field">
                <label>Chroma processor</label>
                <select value={form.chroma_processor_id} onChange={(e) => set('chroma_processor_id', e.target.value)}>
                  <option value="">Select processor</option>
                  {chromaProcessors.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
            )}
            {(form.type === 'salesforce_get' || form.type === 'salesforce_delete') && (
              <>
                <div className="field"><label>Object</label><input value={form.object_template} onChange={(e) => set('object_template', e.target.value)} /></div>
                <div className="field"><label>Id template</label><input value={form.id_template} onChange={(e) => set('id_template', e.target.value)} /></div>
              </>
            )}
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
