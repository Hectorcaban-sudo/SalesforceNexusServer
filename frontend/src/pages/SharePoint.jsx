import { useEffect, useState } from 'react'
import { Plus, Trash2, Pencil, Cloud, RefreshCw, Search } from 'lucide-react'
import api from '../lib/api'

const EMPTY_CONN = { name: '', tenant_id: '', client_id: '', client_secret: '', enabled: true }
const EMPTY_FILE = {
  name: '', connection_id: '', enabled: true,
  site_id: '', drive_id: '',
  folder_path_template: '{{ year }} NBF Reports/{{ business }} Projects',
  file_name_template: '{{ title }}.{{ extension }}',
  create_missing_folders: true, check_in_after_upload: true,
  file_source: 'salesforce_content_version',
  content_document_id_template: '{{ payload.ContentDocumentId }}',
  file_url_template: '',
  metadata_map_text: '{\n  "Title": "{{ title }}"\n}',
  salesforce_record_id_template: '{{ payload.LinkedEntityId }}',
  salesforce_object: 'Opportunity',
}
const EMPTY_LIST = {
  name: '', connection_id: '', enabled: true,
  site_id: '', list_id: '',
  operation: 'create',
  item_id_template: '',
  field_map_text: '{\n  "Title": "{{ payload.Name }}"\n}',
}

function parseMap(text) {
  if (!text || !text.trim()) return {}
  const obj = JSON.parse(text)
  if (typeof obj !== 'object' || Array.isArray(obj)) throw new Error('Map must be a JSON object')
  return obj
}

export default function SharePoint() {
  const [tab, setTab] = useState('connections')
  const [conns, setConns] = useState([])
  const [files, setFiles] = useState([])
  const [lists, setLists] = useState([])
  const [modal, setModal] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  // Graph pickers
  const [sites, setSites] = useState([])
  const [drives, setDrives] = useState([])
  const [spLists, setSpLists] = useState([])
  const [loadingSites, setLoadingSites] = useState(false)
  const [loadingDrives, setLoadingDrives] = useState(false)
  const [loadingLists, setLoadingLists] = useState(false)
  const [siteSearch, setSiteSearch] = useState('*')
  const [sitePathHostname, setSitePathHostname] = useState('')
  const [sitePathRel, setSitePathRel] = useState('')

  async function load() {
    const [c, f, l] = await Promise.all([
      api.get('/sharepoint/connections'),
      api.get('/sharepoint/file-actions'),
      api.get('/sharepoint/list-actions'),
    ])
    setConns(c.data)
    setFiles(f.data)
    setLists(l.data)
  }

  useEffect(() => { load().catch((e) => setError(e.message)) }, [])

  async function loadSites(connectionId, q = '*') {
    if (!connectionId) { setSites([]); return }
    setLoadingSites(true)
    setError(null)
    try {
      const { data } = await api.get(`/sharepoint/connections/${connectionId}/sites`, { params: { q } })
      setSites(data || [])
    } catch (err) {
      setSites([])
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setLoadingSites(false)
    }
  }

  async function resolveSiteByPath(connectionId) {
    if (!connectionId || !sitePathHostname) return
    setLoadingSites(true)
    setError(null)
    try {
      const { data } = await api.get(`/sharepoint/connections/${connectionId}/sites-by-path`, {
        params: { hostname: sitePathHostname, path: sitePathRel || '' },
      })
      setSites((prev) => {
        const exists = prev.some((s) => s.id === data.id)
        return exists ? prev : [data, ...prev]
      })
      setField('site_id', data.id)
      // cascade
      if (modal?.kind === 'file') loadDrives(connectionId, data.id)
      if (modal?.kind === 'list') loadSpLists(connectionId, data.id)
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setLoadingSites(false)
    }
  }

  async function loadDrives(connectionId, siteId) {
    if (!connectionId || !siteId) { setDrives([]); return }
    setLoadingDrives(true)
    try {
      const { data } = await api.get(`/sharepoint/connections/${connectionId}/sites/${encodeURIComponent(siteId)}/drives`)
      setDrives(data || [])
    } catch (err) {
      setDrives([])
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setLoadingDrives(false)
    }
  }

  async function loadSpLists(connectionId, siteId) {
    if (!connectionId || !siteId) { setSpLists([]); return }
    setLoadingLists(true)
    try {
      const { data } = await api.get(`/sharepoint/connections/${connectionId}/sites/${encodeURIComponent(siteId)}/lists`)
      setSpLists(data || [])
    } catch (err) {
      setSpLists([])
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setLoadingLists(false)
    }
  }

  function openCreate(kind) {
    const form = kind === 'conn' ? { ...EMPTY_CONN }
      : kind === 'file' ? { ...EMPTY_FILE, connection_id: conns[0]?.id || '' }
      : { ...EMPTY_LIST, connection_id: conns[0]?.id || '' }
    setModal({ kind, id: null, form })
    setSites([]); setDrives([]); setSpLists([])
    setError(null)
    if (kind !== 'conn' && form.connection_id) loadSites(form.connection_id)
  }

  function openEdit(kind, row) {
    if (kind === 'conn') {
      setModal({ kind, id: row.id, form: { name: row.name, tenant_id: row.tenant_id, client_id: row.client_id, client_secret: '', enabled: row.enabled } })
      setSites([]); setDrives([]); setSpLists([])
    } else if (kind === 'file') {
      setModal({
        kind, id: row.id,
        form: {
          ...EMPTY_FILE,
          ...row,
          metadata_map_text: JSON.stringify(row.metadata_map || {}, null, 2),
        },
      })
      setSites([]); setDrives([]); setSpLists([])
      if (row.connection_id) {
        loadSites(row.connection_id).then(() => {
          if (row.site_id) loadDrives(row.connection_id, row.site_id)
        })
      }
    } else {
      setModal({
        kind, id: row.id,
        form: {
          ...EMPTY_LIST,
          ...row,
          field_map_text: JSON.stringify(row.field_map || {}, null, 2),
        },
      })
      setSites([]); setDrives([]); setSpLists([])
      if (row.connection_id) {
        loadSites(row.connection_id).then(() => {
          if (row.site_id) loadSpLists(row.connection_id, row.site_id)
        })
      }
    }
    setError(null)
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const { kind, id, form } = modal
      if (kind === 'conn') {
        const payload = { ...form }
        if (id) {
          if (!payload.client_secret) delete payload.client_secret
          await api.put(`/sharepoint/connections/${id}`, payload)
        } else {
          await api.post('/sharepoint/connections', payload)
        }
      } else if (kind === 'file') {
        const payload = { ...form }
        payload.metadata_map = parseMap(form.metadata_map_text)
        delete payload.metadata_map_text
        if (id) await api.put(`/sharepoint/file-actions/${id}`, payload)
        else await api.post('/sharepoint/file-actions', payload)
      } else {
        const payload = { ...form }
        payload.field_map = parseMap(form.field_map_text)
        delete payload.field_map_text
        if (id) await api.put(`/sharepoint/list-actions/${id}`, payload)
        else await api.post('/sharepoint/list-actions', payload)
      }
      setModal(null)
      await load()
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setSaving(false)
    }
  }

  async function remove(kind, row) {
    if (!confirm(`Delete "${row.name}"?`)) return
    const path = kind === 'conn' ? `/sharepoint/connections/${row.id}`
      : kind === 'file' ? `/sharepoint/file-actions/${row.id}`
      : `/sharepoint/list-actions/${row.id}`
    await api.delete(path)
    load()
  }

  function setField(key, value) {
    setModal((m) => ({ ...m, form: { ...m.form, [key]: value } }))
  }

  function onConnectionChange(connectionId) {
    setField('connection_id', connectionId)
    setField('site_id', '')
    setField('drive_id', '')
    setField('list_id', '')
    setDrives([]); setSpLists([])
    loadSites(connectionId, siteSearch || '*')
  }

  function onSiteChange(siteId) {
    setField('site_id', siteId)
    setField('drive_id', '')
    setField('list_id', '')
    const connId = modal.form.connection_id
    if (modal.kind === 'file') loadDrives(connId, siteId)
    if (modal.kind === 'list') loadSpLists(connId, siteId)
  }

  const connName = (id) => conns.find((c) => c.id === id)?.name || id
  const siteLabel = (id) => sites.find((s) => s.id === id)?.name || id
  const driveLabel = (id) => drives.find((d) => d.id === id)?.name || id

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>SharePoint Online</h1>
          <p>GCC High connections and reusable File / List processors (Microsoft Graph app-only)</p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {[
          ['connections', 'Connections'],
          ['files', 'File actions'],
          ['lists', 'List actions'],
        ].map(([k, label]) => (
          <button key={k} type="button" className={`btn btn-sm ${tab === k ? 'btn-primary' : ''}`} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </div>

      {error && !modal && <div className="panel" style={{ color: 'var(--accent-red)', marginBottom: 12 }}>{String(error)}</div>}

      {tab === 'connections' && (
        <>
          <div className="page-title-row" style={{ marginBottom: 12 }}>
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 13 }}>Tenant + app registration (client credentials). Cloud is fixed to GCC High.</p>
            <button className="btn btn-primary" onClick={() => openCreate('conn')}><Plus size={15} /> Add connection</button>
          </div>
          <div className="org-grid">
            {conns.length === 0 && <div className="panel"><div className="empty-state">No SharePoint connections yet.</div></div>}
            {conns.map((c) => (
              <div className="panel org-card" key={c.id}>
                <div className="org-card-top">
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <Cloud size={18} color="var(--accent-purple)" />
                    <div>
                      <h4>{c.name}</h4>
                      <div className="url">Tenant {c.tenant_id}</div>
                    </div>
                  </div>
                  <span className={`badge ${c.enabled ? 'badge-green' : 'badge-gray'}`}>{c.enabled ? 'Enabled' : 'Disabled'}</span>
                </div>
                <div className="org-card-meta">
                  <div>Client ID <b style={{ fontSize: 11 }}>{c.client_id}</b></div>
                  <div>Cloud <b>GCC High</b></div>
                </div>
                <div className="org-card-actions">
                  <button className="btn btn-sm" onClick={() => openEdit('conn', c)}><Pencil size={13} /> Edit</button>
                  <button className="btn btn-sm btn-icon btn-danger" onClick={() => remove('conn', c)}><Trash2 size={13} /></button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === 'files' && (
        <>
          <div className="page-title-row" style={{ marginBottom: 12 }}>
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 13 }}>Upload + metadata + check-in. Pick site & library from Graph (no hard-coded IDs required).</p>
            <button className="btn btn-primary" onClick={() => openCreate('file')} disabled={!conns.length}><Plus size={15} /> Add file action</button>
          </div>
          <div className="org-grid">
            {files.length === 0 && <div className="panel"><div className="empty-state">No file actions yet.</div></div>}
            {files.map((f) => (
              <div className="panel org-card" key={f.id}>
                <div className="org-card-top">
                  <div>
                    <h4>{f.name}</h4>
                    <div className="url">{connName(f.connection_id)} · {f.file_source}</div>
                  </div>
                </div>
                <div className="org-card-meta">
                  <div>Folder <b style={{ fontSize: 11 }}>{f.folder_path_template || '—'}</b></div>
                  <div>Drive <b style={{ fontSize: 11 }}>{f.drive_id ? `${f.drive_id.slice(0, 18)}…` : '—'}</b></div>
                </div>
                <div className="org-card-actions">
                  <button className="btn btn-sm" onClick={() => openEdit('file', f)}><Pencil size={13} /> Edit</button>
                  <button className="btn btn-sm btn-icon btn-danger" onClick={() => remove('file', f)}><Trash2 size={13} /></button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === 'lists' && (
        <>
          <div className="page-title-row" style={{ marginBottom: 12 }}>
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 13 }}>Create or update list items. Pick site & list from Graph dropdowns.</p>
            <button className="btn btn-primary" onClick={() => openCreate('list')} disabled={!conns.length}><Plus size={15} /> Add list action</button>
          </div>
          <div className="org-grid">
            {lists.length === 0 && <div className="panel"><div className="empty-state">No list actions yet.</div></div>}
            {lists.map((f) => (
              <div className="panel org-card" key={f.id}>
                <div className="org-card-top">
                  <div>
                    <h4>{f.name}</h4>
                    <div className="url">{connName(f.connection_id)} · {f.operation}</div>
                  </div>
                </div>
                <div className="org-card-actions">
                  <button className="btn btn-sm" onClick={() => openEdit('list', f)}><Pencil size={13} /> Edit</button>
                  <button className="btn btn-sm btn-icon btn-danger" onClick={() => remove('list', f)}><Trash2 size={13} /></button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-box" style={{ maxWidth: 680 }} onClick={(e) => e.stopPropagation()}>
            <div className="panel-header">
              <h3>
                {modal.id ? 'Edit' : 'Add'}{' '}
                {modal.kind === 'conn' ? 'connection' : modal.kind === 'file' ? 'file action' : 'list action'}
              </h3>
            </div>
            <form onSubmit={save}>
              <div className="panel-body">
                {error && <div style={{ color: 'var(--accent-red)', fontSize: 13, marginBottom: 10 }}>{String(error)}</div>}

                {modal.kind === 'conn' && (
                  <>
                    <div className="field"><label>Name</label>
                      <input required value={modal.form.name} onChange={(e) => setField('name', e.target.value)} /></div>
                    <div className="field"><label>Tenant ID</label>
                      <input required value={modal.form.tenant_id} onChange={(e) => setField('tenant_id', e.target.value)} /></div>
                    <div className="field"><label>Client ID</label>
                      <input required value={modal.form.client_id} onChange={(e) => setField('client_id', e.target.value)} /></div>
                    <div className="field"><label>Client secret {modal.id && '(leave blank to keep existing)'}</label>
                      <input type="password" value={modal.form.client_secret} onChange={(e) => setField('client_secret', e.target.value)} required={!modal.id} /></div>
                    <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>Cloud is fixed to <b>GCC High</b> (graph.microsoft.us).</p>
                  </>
                )}

                {(modal.kind === 'file' || modal.kind === 'list') && (
                  <>
                    <div className="field"><label>Name</label>
                      <input required value={modal.form.name} onChange={(e) => setField('name', e.target.value)} /></div>

                    <div className="field"><label>Connection</label>
                      <select required value={modal.form.connection_id} onChange={(e) => onConnectionChange(e.target.value)}>
                        <option value="">Select connection…</option>
                        {conns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                    </div>

                    {/* Site picker */}
                    <div className="field">
                      <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span>Site</span>
                        <span style={{ fontWeight: 400, fontSize: 11, color: 'var(--text-muted)' }}>
                          {loadingSites ? 'Loading…' : `${sites.length} found`}
                        </span>
                      </label>
                      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                        <input
                          value={siteSearch}
                          onChange={(e) => setSiteSearch(e.target.value)}
                          placeholder="Search sites (e.g. NBF or *)"
                          style={{ flex: 1 }}
                        />
                        <button
                          type="button"
                          className="btn btn-sm"
                          disabled={!modal.form.connection_id || loadingSites}
                          onClick={() => loadSites(modal.form.connection_id, siteSearch || '*')}
                        >
                          <Search size={13} /> Search
                        </button>
                      </div>
                      <select
                        required
                        value={modal.form.site_id}
                        onChange={(e) => onSiteChange(e.target.value)}
                        disabled={!modal.form.connection_id}
                      >
                        <option value="">Select a site…</option>
                        {modal.form.site_id && !sites.some((s) => s.id === modal.form.site_id) && (
                          <option value={modal.form.site_id}>{modal.form.site_id} (saved)</option>
                        )}
                        {sites.map((s) => (
                          <option key={s.id} value={s.id}>{s.name}{s.web_url ? ` — ${s.web_url}` : ''}</option>
                        ))}
                      </select>
                      <details style={{ marginTop: 8 }}>
                        <summary style={{ fontSize: 12, color: 'var(--text-muted)', cursor: 'pointer' }}>
                          Or resolve by hostname + path (Power Automate style)
                        </summary>
                        <div className="form-row-2" style={{ marginTop: 8 }}>
                          <div className="field" style={{ marginBottom: 0 }}>
                            <label>Hostname</label>
                            <input
                              value={sitePathHostname}
                              onChange={(e) => setSitePathHostname(e.target.value)}
                              placeholder="contoso.sharepoint.us"
                            />
                          </div>
                          <div className="field" style={{ marginBottom: 0 }}>
                            <label>Server-relative path</label>
                            <input
                              value={sitePathRel}
                              onChange={(e) => setSitePathRel(e.target.value)}
                              placeholder="sites/IS-HQ_InSNBF"
                            />
                          </div>
                        </div>
                        <button
                          type="button"
                          className="btn btn-sm"
                          style={{ marginTop: 8 }}
                          disabled={!modal.form.connection_id || !sitePathHostname}
                          onClick={() => resolveSiteByPath(modal.form.connection_id)}
                        >
                          <RefreshCw size={13} /> Resolve site
                        </button>
                      </details>
                    </div>

                    {modal.kind === 'file' && (
                      <div className="field">
                        <label style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Document library (Drive)</span>
                          <span style={{ fontWeight: 400, fontSize: 11, color: 'var(--text-muted)' }}>
                            {loadingDrives ? 'Loading…' : `${drives.length} libraries`}
                          </span>
                        </label>
                        <select
                          required
                          value={modal.form.drive_id}
                          onChange={(e) => setField('drive_id', e.target.value)}
                          disabled={!modal.form.site_id}
                        >
                          <option value="">Select a library…</option>
                          {modal.form.drive_id && !drives.some((d) => d.id === modal.form.drive_id) && (
                            <option value={modal.form.drive_id}>{modal.form.drive_id} (saved)</option>
                          )}
                          {drives.map((d) => (
                            <option key={d.id} value={d.id}>{d.name}{d.drive_type ? ` (${d.drive_type})` : ''}</option>
                          ))}
                        </select>
                      </div>
                    )}

                    {modal.kind === 'list' && (
                      <div className="field">
                        <label style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>List</span>
                          <span style={{ fontWeight: 400, fontSize: 11, color: 'var(--text-muted)' }}>
                            {loadingLists ? 'Loading…' : `${spLists.length} lists`}
                          </span>
                        </label>
                        <select
                          required
                          value={modal.form.list_id}
                          onChange={(e) => setField('list_id', e.target.value)}
                          disabled={!modal.form.site_id}
                        >
                          <option value="">Select a list…</option>
                          {modal.form.list_id && !spLists.some((l) => l.id === modal.form.list_id) && (
                            <option value={modal.form.list_id}>{modal.form.list_id} (saved)</option>
                          )}
                          {spLists.map((l) => (
                            <option key={l.id} value={l.id}>{l.name}</option>
                          ))}
                        </select>
                      </div>
                    )}
                  </>
                )}

                {modal.kind === 'file' && (
                  <>
                    <div className="field"><label>Folder path (Jinja2)</label>
                      <input value={modal.form.folder_path_template} onChange={(e) => setField('folder_path_template', e.target.value)} /></div>
                    <div className="field"><label>File name (Jinja2)</label>
                      <input value={modal.form.file_name_template} onChange={(e) => setField('file_name_template', e.target.value)} /></div>
                    <div className="field"><label>File source</label>
                      <select value={modal.form.file_source} onChange={(e) => setField('file_source', e.target.value)}>
                        <option value="salesforce_content_version">Salesforce ContentVersion</option>
                        <option value="url">URL</option>
                      </select>
                    </div>
                    {modal.form.file_source === 'salesforce_content_version' ? (
                      <div className="field"><label>ContentDocumentId template</label>
                        <input value={modal.form.content_document_id_template} onChange={(e) => setField('content_document_id_template', e.target.value)} /></div>
                    ) : (
                      <div className="field"><label>File URL template</label>
                        <input value={modal.form.file_url_template} onChange={(e) => setField('file_url_template', e.target.value)} /></div>
                    )}
                    <div className="form-row-2">
                      <div className="field"><label>SF record Id template (optional)</label>
                        <input value={modal.form.salesforce_record_id_template} onChange={(e) => setField('salesforce_record_id_template', e.target.value)} /></div>
                      <div className="field"><label>SF object API name</label>
                        <input value={modal.form.salesforce_object} onChange={(e) => setField('salesforce_object', e.target.value)} /></div>
                    </div>
                    <div className="field"><label>Metadata map (JSON column → Jinja2)</label>
                      <textarea rows={5} value={modal.form.metadata_map_text} onChange={(e) => setField('metadata_map_text', e.target.value)}
                        style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12.5 }} /></div>
                    <div className="field" style={{ display: 'flex', gap: 16 }}>
                      <label style={{ display: 'flex', gap: 6, alignItems: 'center', margin: 0 }}>
                        <input type="checkbox" checked={modal.form.create_missing_folders} onChange={(e) => setField('create_missing_folders', e.target.checked)} style={{ width: 16 }} />
                        Create missing folders
                      </label>
                      <label style={{ display: 'flex', gap: 6, alignItems: 'center', margin: 0 }}>
                        <input type="checkbox" checked={modal.form.check_in_after_upload} onChange={(e) => setField('check_in_after_upload', e.target.checked)} style={{ width: 16 }} />
                        Check in after upload
                      </label>
                    </div>
                  </>
                )}

                {modal.kind === 'list' && (
                  <>
                    <div className="field"><label>Operation</label>
                      <select value={modal.form.operation} onChange={(e) => setField('operation', e.target.value)}>
                        <option value="create">Create</option>
                        <option value="update">Update</option>
                      </select>
                    </div>
                    {modal.form.operation === 'update' && (
                      <div className="field"><label>Item ID template (Jinja2)</label>
                        <input value={modal.form.item_id_template} onChange={(e) => setField('item_id_template', e.target.value)} /></div>
                    )}
                    <div className="field"><label>Field map (JSON field → Jinja2)</label>
                      <textarea rows={5} value={modal.form.field_map_text} onChange={(e) => setField('field_map_text', e.target.value)}
                        style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12.5 }} /></div>
                  </>
                )}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setModal(null)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
