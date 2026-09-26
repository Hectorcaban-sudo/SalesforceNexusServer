import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import {
  ReactFlow, Background, Controls, MiniMap, Handle, Position,
  useNodesState, useEdgesState, addEdge, MarkerType, ReactFlowProvider, useReactFlow,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  ArrowLeft, Save, Radio, ShieldCheck, Cpu, ArrowUpFromLine,
  Share2, BellRing, X, FileJson, Wand2, Map, Ban, GripVertical, GitBranch,
  LayoutTemplate, Download, Play,
} from 'lucide-react'
import api from '../lib/api'
import { isGlobalResource, useProject } from '../lib/ProjectContext'

function libraryOptionLabel(row) {
  if (!row) return ''
  return isGlobalResource(row) ? `🌐 ${row.name}` : row.name
}

const PALETTE = [
  { type: 'schema', label: 'Schema', icon: FileJson, accent: '#06b6d4', once: true },
  { type: 'rule', label: 'Choice / Rule', icon: ShieldCheck, accent: '#a78bfa', once: true },
  { type: 'processor', label: 'Processor', icon: Cpu, accent: '#3b82f6', once: true },
  { type: 'transform', label: 'Transform', icon: Wand2, accent: '#eab308', once: true },
  { type: 'publishMap', label: 'Publish map', icon: Map, accent: '#14b8a6', once: true },
  { type: 'publish', label: 'Publish', icon: ArrowUpFromLine, accent: '#22c55e', once: false },
  { type: 'integration', label: 'Integration', icon: Share2, accent: '#8b5cf6', once: false },
  { type: 'alert', label: 'Alert', icon: BellRing, accent: '#ef4444', once: false },
  { type: 'stop', label: 'Stop', icon: Ban, accent: '#f43f5e', once: false },
  { type: 'if', label: 'If / else', icon: GitBranch, accent: '#f59e0b', once: false },
  { type: 'switch', label: 'Switch', icon: GitBranch, accent: '#fb7185', once: false },
]

const defaultEdgeOptions = {
  type: 'smoothstep',
  style: { stroke: '#64748b', strokeWidth: 1.5 },
  markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: '#64748b' },
}

function NodeShell({ accent, icon: Icon, title, subtitle, badge, selected }) {
  return (
    <div className={`flow-node ${selected ? 'selected' : ''}`} style={{ '--node-accent': accent }}>
      <Handle type="target" position={Position.Left} className="flow-handle" />
      <div className="flow-node-head">
        <div className="flow-node-icon" style={{ background: `${accent}22`, color: accent }}>
          <Icon size={14} />
        </div>
        <div className="flow-node-titles">
          <div className="flow-node-title">{title}</div>
          {subtitle && <div className="flow-node-sub">{subtitle}</div>}
        </div>
      </div>
      {badge && <div className="flow-node-badge">{badge}</div>}
      <Handle type="source" position={Position.Right} className="flow-handle" />
    </div>
  )
}

function makeNodeComponent(meta) {
  return function FlowNode({ data, selected }) {
    return (
      <NodeShell
        accent={meta.accent}
        icon={meta.icon}
        title={data.label || meta.label}
        subtitle={data.subtitle}
        badge={data.badge}
        selected={selected}
      />
    )
  }
}

function BranchNode({ data, selected, accent, icon: Icon, handles }) {
  return (
    <div className={`flow-node ${selected ? 'selected' : ''}`} style={{ '--node-accent': accent }}>
      <Handle type="target" position={Position.Left} className="flow-handle" />
      <div className="flow-node-head">
        <div className="flow-node-icon" style={{ background: `${accent}22`, color: accent }}>
          <Icon size={14} />
        </div>
        <div className="flow-node-titles">
          <div className="flow-node-title">{data.label}</div>
          {data.subtitle && <div className="flow-node-sub">{data.subtitle}</div>}
        </div>
      </div>
      {handles.map((h, i) => (
        <Handle key={h.id} type="source" position={Position.Right} id={h.id} className="flow-handle"
          style={{ top: 24 + i * 16 }} title={h.label} />
      ))}
    </div>
  )
}

const nodeTypes = Object.fromEntries(PALETTE.filter((p) => !['if', 'switch'].includes(p.type)).map((p) => [p.type, makeNodeComponent(p)]))
nodeTypes.source = makeNodeComponent({ accent: '#f97316', icon: Radio, label: 'Source' })
nodeTypes.if = function IfFlowNode({ data, selected }) {
  return <BranchNode data={data} selected={selected} accent="#f59e0b" icon={GitBranch}
    handles={[{ id: 'true', label: 'true' }, { id: 'false', label: 'false' }]} />
}
nodeTypes.switch = function SwitchFlowNode({ data, selected }) {
  const cases = String(data.switchCases || 'default').split(',').map((s) => s.trim()).filter(Boolean)
  const handles = [...new Set(cases.concat(['default']))].map((c) => ({ id: c, label: c }))
  return <BranchNode data={data} selected={selected} accent="#fb7185" icon={GitBranch} handles={handles} />
}

function graphFromEvent(event, refs) {
  const { rules, pubs, integrations, alerts } = refs
  const nodes = []
  const edges = []
  let x = 40
  const y = 200
  const step = 220

  nodes.push({
    id: 'source', type: 'source', position: { x, y },
    data: { label: event.channel, subtitle: 'Subscribe', badge: event.enabled ? 'On' : 'Off' },
    draggable: true,
  })
  x += step

  const schemaMode = event.schema_validation_mode || 'off'
  nodes.push({
    id: 'schema', type: 'schema', position: { x, y },
    data: {
      label: 'Schema', subtitle: schemaMode, badge: schemaMode === 'reject' ? 'Reject' : schemaMode,
      schemaMode,
      samplePayloadText: event.sample_payload ? JSON.stringify(event.sample_payload, null, 2) : '',
      payloadSchemaText: event.payload_schema ? JSON.stringify(event.payload_schema, null, 2) : '',
    },
    draggable: true,
  })
  edges.push({ id: 'e-src-schema', source: 'source', target: 'schema', ...defaultEdgeOptions })
  x += step

  const rule = rules.find((r) => r.id === event.rule_id)
  nodes.push({
    id: 'rule', type: 'rule', position: { x, y },
    data: { label: rule?.name || 'Choice', subtitle: rule ? 'GoRules' : 'Always', ruleId: event.rule_id || '' },
    draggable: true,
  })
  edges.push({ id: 'e-schema-rule', source: 'schema', target: 'rule', ...defaultEdgeOptions })
  x += step

  const mode = event.processing_mode || ''
  nodes.push({
    id: 'processor', type: 'processor', position: { x, y },
    data: {
      label: mode || 'Global default',
      subtitle: event.processor_id ? String(event.processor_id).slice(0, 10) : 'Processor',
      processingMode: mode, processorId: event.processor_id || '',
    },
    draggable: true,
  })
  edges.push({ id: 'e-rule-proc', source: 'rule', target: 'processor', ...defaultEdgeOptions })
  x += step

  nodes.push({
    id: 'transform', type: 'transform', position: { x, y },
    data: {
      label: 'Transform', subtitle: event.result_transform_template ? 'Jinja on' : 'Off',
      resultTransform: event.result_transform_template || '',
    },
    draggable: true,
  })
  edges.push({ id: 'e-proc-xf', source: 'processor', target: 'transform', ...defaultEdgeOptions })
  x += step

  const fmap = event.publish_field_map || {}
  nodes.push({
    id: 'publishMap', type: 'publishMap', position: { x, y },
    data: {
      label: 'Publish map', subtitle: Object.keys(fmap).length ? 'Mapped' : 'Raw',
      publishMapText: JSON.stringify(fmap, null, 2),
    },
    draggable: true,
  })
  edges.push({ id: 'e-xf-map', source: 'transform', target: 'publishMap', ...defaultEdgeOptions })
  x += step

  let fanY = 60
  if (event.auto_publish === false) {
    nodes.push({ id: 'stop', type: 'stop', position: { x, y: fanY }, data: { label: 'Stop publish', subtitle: 'No SF publish' }, draggable: true })
    edges.push({ id: 'e-map-stop', source: 'publishMap', target: 'stop', ...defaultEdgeOptions })
    fanY += 110
  }

  ;(event.route_publish_channel_ids || []).forEach((id) => {
    const ch = pubs.find((x) => x.id === id)
    const nid = `publish-${id}`
    nodes.push({ id: nid, type: 'publish', position: { x, y: fanY }, data: { label: ch?.channel || id, subtitle: 'Publish', refId: id }, draggable: true })
    edges.push({ id: `e-map-${nid}`, source: 'publishMap', target: nid, ...defaultEdgeOptions })
    fanY += 110
  })
  ;(event.route_integration_ids || []).forEach((id) => {
    const i = integrations.find((x) => x.id === id)
    const nid = `integration-${id}`
    nodes.push({ id: nid, type: 'integration', position: { x, y: fanY }, data: { label: i?.name || id, subtitle: i?.type || 'Integration', refId: id }, draggable: true })
    edges.push({ id: `e-map-${nid}`, source: 'publishMap', target: nid, ...defaultEdgeOptions })
    fanY += 110
  })
  ;(event.route_alert_ids || []).forEach((id) => {
    const a = alerts.find((x) => x.id === id)
    const nid = `alert-${id}`
    nodes.push({ id: nid, type: 'alert', position: { x, y: fanY }, data: { label: a?.name || id, subtitle: 'Alert', refId: id }, draggable: true })
    edges.push({ id: `e-map-${nid}`, source: 'publishMap', target: nid, ...defaultEdgeOptions })
    fanY += 110
  })

  return { nodes, edges }
}

function configFromGraph(nodes) {
  const byType = (t) => nodes.filter((n) => n.type === t)
  const one = (t) => byType(t)[0]
  const schema = one('schema')
  const rule = one('rule')
  const processor = one('processor')
  const transform = one('transform')
  const publishMap = one('publishMap')
  const stop = one('stop')

  let sample_payload = null
  let payload_schema = null
  let publish_field_map = {}
  try {
    if (schema?.data?.samplePayloadText?.trim()) sample_payload = JSON.parse(schema.data.samplePayloadText)
  } catch {}
  try {
    if (schema?.data?.payloadSchemaText?.trim()) payload_schema = JSON.parse(schema.data.payloadSchemaText)
  } catch {}
  try {
    if (publishMap?.data?.publishMapText?.trim()) publish_field_map = JSON.parse(publishMap.data.publishMapText)
  } catch { publish_field_map = {} }

  return {
    rule_id: rule?.data?.ruleId || '',
    processing_mode: processor?.data?.processingMode || '',
    processor_id: processor?.data?.processorId || '',
    auto_publish: !stop,
    result_transform_template: transform?.data?.resultTransform || '',
    sample_payload,
    payload_schema,
    schema_validation_mode: schema?.data?.schemaMode || 'off',
    publish_field_map,
    route_publish_channel_ids: byType('publish').map((n) => n.data.refId).filter(Boolean),
    route_integration_ids: byType('integration').map((n) => n.data.refId).filter(Boolean),
    route_alert_ids: byType('alert').map((n) => n.data.refId).filter(Boolean),
  }
}

function NodeConfigModal({ node, refs, onClose, onSave, panel }) {
  const [data, setData] = useState({ ...(node?.data || {}) })
  const [msg, setMsg] = useState(null)
  if (!node) return null
  const type = node.type

  async function inferSchema() {
    try {
      const sample = JSON.parse(data.samplePayloadText || '{}')
      const { data: res } = await api.post('/events/schema/infer', { sample })
      setData((d) => ({ ...d, payloadSchemaText: JSON.stringify(res.schema, null, 2) }))
      setMsg({ ok: true, text: 'Schema inferred' })
    } catch (err) {
      setMsg({ ok: false, text: err?.response?.data?.detail || err.message })
    }
  }

  async function validateSample() {
    try {
      const payload = JSON.parse(data.samplePayloadText || '{}')
      const schema = data.payloadSchemaText?.trim() ? JSON.parse(data.payloadSchemaText) : null
      const { data: res } = await api.post('/events/schema/validate', { payload, schema })
      setMsg({ ok: res.ok, text: res.ok ? 'Valid' : (res.errors || []).join('; ') })
    } catch (err) {
      setMsg({ ok: false, text: err?.response?.data?.detail || err.message })
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ maxWidth: 560 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between' }}>
          <h2>Configure: {type}</h2>
          <button type="button" className="btn btn-sm" onClick={onClose}><X size={14} /></button>
        </div>
        <div className="modal-body">
          {type === 'schema' && (
            <>
              <div className="field">
                <label>Validation mode</label>
                <select value={data.schemaMode || 'off'} onChange={(e) => setData({ ...data, schemaMode: e.target.value })}>
                  <option value="off">Off</option>
                  <option value="warn">Warn</option>
                  <option value="reject">Reject on fail</option>
                </select>
              </div>
              <div className="field">
                <label>Sample payload</label>
                <textarea rows={5} value={data.samplePayloadText || ''} onChange={(e) => setData({ ...data, samplePayloadText: e.target.value })}
                  style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12 }} />
              </div>
              <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                <button type="button" className="btn btn-sm" onClick={inferSchema}>Infer schema</button>
                <button type="button" className="btn btn-sm" onClick={validateSample}>Validate sample</button>
              </div>
              {msg && <p style={{ fontSize: 12, color: msg.ok ? 'var(--accent-green,#22c55e)' : 'var(--accent-red)' }}>{msg.text}</p>}
              <div className="field">
                <label>JSON Schema</label>
                <textarea rows={6} value={data.payloadSchemaText || ''} onChange={(e) => setData({ ...data, payloadSchemaText: e.target.value })}
                  style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12 }} />
              </div>
            </>
          )}
          {type === 'rule' && (
            <div className="field">
              <label>Rule (choice gate)</label>
              <select value={data.ruleId || ''} onChange={(e) => setData({ ...data, ruleId: e.target.value, label: refs.rules.find((r) => r.id === e.target.value)?.name || 'Choice' })}>
                <option value="">Always process</option>
                {refs.rules.map((r) => <option key={r.id} value={r.id}>{libraryOptionLabel(r)}</option>)}
              </select>
            </div>
          )}
          {type === 'processor' && (
            <>
              <div className="field">
                <label>Processing mode</label>
                <select value={data.processingMode || ''} onChange={(e) => setData({ ...data, processingMode: e.target.value, label: e.target.value || 'Global default' })}>
                  <option value="">Global default</option>
                  <option value="local">Local</option>
                  <option value="dss_client">Dataiku DSS</option>
                  <option value="langflow">Langflow</option>
                  <option value="custom_script">Custom script</option>
                  <option value="sharepoint_file">SharePoint File</option>
                  <option value="sharepoint_list">SharePoint List</option>
                </select>
              </div>
              {data.processingMode === 'custom_script' && (
                <div className="field">
                  <label>Processor</label>
                  <select value={data.processorId || ''} onChange={(e) => setData({ ...data, processorId: e.target.value })}>
                    <option value="">Select…</option>
                    {refs.processors.map((p) => <option key={p.id} value={p.id}>{libraryOptionLabel(p)}</option>)}
                  </select>
                </div>
              )}
              {data.processingMode === 'sharepoint_file' && (
                <div className="field">
                  <label>File action</label>
                  <select value={data.processorId || ''} onChange={(e) => setData({ ...data, processorId: e.target.value })}>
                    <option value="">Select…</option>
                    {refs.spFileActions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </div>
              )}
              {data.processingMode === 'sharepoint_list' && (
                <div className="field">
                  <label>List action</label>
                  <select value={data.processorId || ''} onChange={(e) => setData({ ...data, processorId: e.target.value })}>
                    <option value="">Select…</option>
                    {refs.spListActions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </div>
              )}
            </>
          )}
          {type === 'transform' && (
            <div className="field">
              <label>Jinja2 transform</label>
              <textarea rows={6} value={data.resultTransform || ''} onChange={(e) => setData({ ...data, resultTransform: e.target.value })}
                style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12 }} />
            </div>
          )}
          {type === 'publishMap' && (
            <div className="field">
              <label>Publish field map (JSON)</label>
              <textarea rows={8} value={data.publishMapText || '{}'} onChange={(e) => setData({ ...data, publishMapText: e.target.value })}
                style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12 }} />
            </div>
          )}
          {type === 'publish' && (
            <div className="field">
              <label>Publish channel</label>
              <select value={data.refId || ''} onChange={(e) => {
                const ch = refs.pubs.find((x) => x.id === e.target.value)
                setData({ ...data, refId: e.target.value, label: ch?.channel || e.target.value })
              }}>
                <option value="">Select…</option>
                {refs.pubs.map((p) => <option key={p.id} value={p.id}>{p.channel}</option>)}
              </select>
            </div>
          )}
          {type === 'integration' && (
            <div className="field">
              <label>Integration</label>
              <select value={data.refId || ''} onChange={(e) => {
                const i = refs.integrations.find((x) => x.id === e.target.value)
                setData({ ...data, refId: e.target.value, label: i?.name || e.target.value, subtitle: i?.type })
              }}>
                <option value="">Select…</option>
                {refs.integrations.filter((i) => !i.alert_only).map((i) => (
                  <option key={i.id} value={i.id}>{i.name} ({i.type})</option>
                ))}
              </select>
            </div>
          )}
          {type === 'alert' && (
            <div className="field">
              <label>Alert</label>
              <select value={data.refId || ''} onChange={(e) => {
                const a = refs.alerts.find((x) => x.id === e.target.value)
                setData({ ...data, refId: e.target.value, label: a?.name || e.target.value })
              }}>
                <option value="">Select…</option>
                {refs.alerts.filter((a) => a.scope === 'transaction').map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
            </div>
          )}
          {type === 'stop' && (
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              Hard stop: nothing after this node runs. Integrations already visited have already fired. Salesforce publish nodes after this are skipped.
            </p>
          )}
          {type === 'if' && (
            <>
              <div className="field">
                <label>Field (payload.Status or result.status)</label>
                <input value={data.condField || 'payload.Status'} onChange={(e) => setData({ ...data, condField: e.target.value, subtitle: e.target.value })} />
              </div>
              <div className="field">
                <label>Operator</label>
                <select value={data.condOp || 'eq'} onChange={(e) => setData({ ...data, condOp: e.target.value })}>
                  <option value="eq">equals</option>
                  <option value="ne">not equals</option>
                  <option value="contains">contains</option>
                  <option value="exists">exists</option>
                  <option value="gt">greater than</option>
                  <option value="lt">less than</option>
                </select>
              </div>
              <div className="field">
                <label>Value</label>
                <input value={data.condValue || ''} onChange={(e) => setData({ ...data, condValue: e.target.value })} />
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>Connect the <b>true</b> handle and <b>false</b> handle to different branches.</p>
            </>
          )}
          {type === 'switch' && (
            <>
              <div className="field">
                <label>Field</label>
                <input value={data.switchField || 'payload.Type'} onChange={(e) => setData({ ...data, switchField: e.target.value, subtitle: e.target.value })} />
              </div>
              <div className="field">
                <label>Cases (comma-separated) + default</label>
                <input value={data.switchCases || 'A,B,default'} onChange={(e) => setData({ ...data, switchCases: e.target.value })} />
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>Each case name is a source handle. Unmatched values use <b>default</b>.</p>
            </>
          )}
          {type === 'source' && (
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>Subscribe channel is fixed for this flow.</p>
          )}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-primary" onClick={() => onSave(data)}>Save node</button>
        </div>
      </div>
    </div>
  )
}

function FlowCanvasInner({ event, refs }) {
  const { screenToFlowPosition } = useReactFlow()
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [modalNode, setModalNode] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [dirty, setDirty] = useState(false)
  const [tplOpen, setTplOpen] = useState(false)
  const [tplName, setTplName] = useState('')
  const [tplDesc, setTplDesc] = useState('')
  const [tplGlobal, setTplGlobal] = useState(false)
  const [tplPlaceholders, setTplPlaceholders] = useState(true)
  const [tplSaving, setTplSaving] = useState(false)
  const [applyOpen, setApplyOpen] = useState(false)
  const [templates, setTemplates] = useState([])
  const [testOpen, setTestOpen] = useState(false)
  const [testJson, setTestJson] = useState('{\n  "Status": "Closed"\n}')
  const [testResult, setTestResult] = useState(null)
  const [testRunning, setTestRunning] = useState(false)
  const navigate = useNavigate()
  const { projectId } = useProject()

  useEffect(() => {
    if (!event) return
    if (event.flow_graph && Array.isArray(event.flow_graph.nodes) && event.flow_graph.nodes.length) {
      setNodes(event.flow_graph.nodes)
      setEdges(event.flow_graph.edges || [])
    } else {
      const g = graphFromEvent(event, refs)
      setNodes(g.nodes)
      setEdges(g.edges)
    }
    setDirty(false)
  }, [event, refs])

  const onConnect = useCallback((params) => {
    setEdges((eds) => addEdge({ ...params, ...defaultEdgeOptions }, eds))
    setDirty(true)
  }, [setEdges])

  const onDragOver = useCallback((e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback((e) => {
    e.preventDefault()
    const type = e.dataTransfer.getData('application/nexus-node')
    if (!type) return
    const meta = PALETTE.find((p) => p.type === type)
    if (!meta) return
    if (meta.once && nodes.some((n) => n.type === type)) {
      setError(`Only one "${meta.label}" node is allowed`)
      return
    }
    const position = screenToFlowPosition({ x: e.clientX, y: e.clientY })
    const id = meta.once ? type : `${type}-${Date.now()}`
    const newNode = { id, type, position, data: { label: meta.label, subtitle: 'Configure…' }, draggable: true }
    setNodes((nds) => nds.concat(newNode))
    setDirty(true)
    setModalNode(newNode)
  }, [nodes, screenToFlowPosition, setNodes])

  function saveNodeData(data) {
    setNodes((nds) => nds.map((n) => (n.id === modalNode.id ? { ...n, data: { ...n.data, ...data } } : n)))
    setModalNode(null)
    setDirty(true)
  }

  async function saveFlow() {
    setSaving(true)
    setError(null)
    try {
      const payload = {
        ...configFromGraph(nodes),
        flow_graph: { nodes, edges },
      }
      if (event._pipelineId) {
        await api.put(`/events/${event.id}/pipelines/${event._pipelineId}`, { flow_graph: { nodes, edges } })
      } else {
        await api.put(`/events/${event.id}`, payload)
      }
      setDirty(false)
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setSaving(false)
    }
  }

  async function saveTemplate(e) {
    e.preventDefault()
    setTplSaving(true)
    setError(null)
    try {
      await api.post('/flow-templates', {
        name: tplName,
        description: tplDesc,
        project_id: tplGlobal ? null : (projectId || null),
        placeholders: tplPlaceholders,
        graph: { nodes, edges },
      })
      setTplOpen(false)
      setTplName('')
      setTplDesc('')
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setTplSaving(false)
    }
  }

  async function openApply() {
    const lib = projectId ? { project_id: projectId, include_global: true } : {}
    const { data } = await api.get('/flow-templates', { params: lib })
    setTemplates(data || [])
    setApplyOpen(true)
  }

  function applyTemplate(tpl) {
    const g = tpl.graph || {}
    if (!g.nodes?.length) return
    setNodes(g.nodes)
    setEdges(g.edges || [])
    setDirty(true)
    setApplyOpen(false)
  }

  function exportPdf() {
    const w = window.open('', '_blank', 'noopener,width=900,height=700')
    if (!w) return
    const rows = nodes.map((n) => {
      const d = n.data || {}
      return `<tr><td>${d.label || n.type}</td><td>${n.type}</td><td>${d.subtitle || d.refId || ''}</td><td>${Math.round(n.position?.x || 0)}, ${Math.round(n.position?.y || 0)}</td></tr>`
    }).join('')
    w.document.write(`<!doctype html><html><head><title>${event?.channel || 'flow'}</title>
      <style>body{font-family:system-ui,sans-serif;padding:24px;color:#111}
      h1{font-size:20px} table{border-collapse:collapse;width:100%;font-size:13px}
      th,td{border:1px solid #ccc;padding:6px 8px;text-align:left} th{background:#f3f4f6}
      .muted{color:#666;font-size:12px}</style></head><body>
      <p class="muted">Nexus pipeline · ${new Date().toISOString()}</p>
      <h1>${event?.channel || 'Flow'}</h1>
      <p>${nodes.length} nodes · ${edges.length} edges · layout snapshot (not Visio)</p>
      <table><thead><tr><th>Node</th><th>Type</th><th>Detail</th><th>Position</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <script>window.onload=()=>window.print()<\/script></body></html>`)
    w.document.close()
  }

  async function runDryTest(e) {
    e.preventDefault()
    setTestRunning(true)
    setTestResult(null)
    setError(null)
    try {
      const payload = JSON.parse(testJson)
      const { data } = await api.post(`/events/${event.id}/dry-run`, {
        payload,
        graph: { nodes, edges },
      })
      setTestResult(data)
    } catch (err) {
      setTestResult({ ok: false, error: err?.response?.data?.detail || err.message, steps: [] })
    } finally {
      setTestRunning(false)
    }
  }

  function onDragStart(e, type) {
    e.dataTransfer.setData('application/nexus-node', type)
    e.dataTransfer.effectAllowed = 'move'
  }

  return (
    <div className="flow-page">
      <div className="flow-toolbar">
        <div className="flow-toolbar-left">
          <button type="button" className="btn btn-sm" onClick={() => navigate(event?.id ? `/events/${event.id}/pipelines` : '/events')}>
            <ArrowLeft size={14} /> Back to Events
          </button>
          <div>
            <div className="flow-breadcrumb">Events / Flow</div>
            <h1 className="flow-title">{event?._pipelineName || event?.channel} / Flow</h1>
            <p className="flow-subtitle">Worker walks this graph. Integrations fire when visited. Stop aborts remaining nodes.</p>
            {(event?._pipelines || []).length > 1 && (
              <select className="input" style={{ marginTop: 8 }} value={event._pipelineId || ''}
                onChange={(e) => navigate(`/events/${event.id}/pipelines/${e.target.value}/flow`)}>
                {event._pipelines.map((pl) => <option key={pl.id} value={pl.id}>{pl.name}{pl.enabled ? '' : ' (off)'}</option>)}
              </select>
            )}
          </div>
        </div>
        <div className="flow-toolbar-right">
          {dirty && <span className="flow-dirty">Unsaved</span>}
          <button type="button" className="btn btn-sm" onClick={() => { setTplName(`${event?.channel || 'flow'} template`); setTplOpen(true) }}>
            <LayoutTemplate size={14} /> Save as template
          </button>
          <button type="button" className="btn btn-sm" onClick={openApply}>Apply template</button>
          <button type="button" className="btn btn-sm" onClick={exportPdf}>
            <Download size={14} /> Export PDF
          </button>
          <button type="button" className="btn btn-sm" onClick={() => { setTestOpen(true); setTestResult(null) }}>
            <Play size={14} /> Test
          </button>
          <button type="button" className="btn btn-primary" onClick={saveFlow} disabled={!dirty || saving}>
            <Save size={14} /> {saving ? 'Saving…' : 'Save flow'}
          </button>
        </div>
      </div>
      {error && <div className="flow-error">{error}</div>}
      <div className="flow-body">
        <aside className="flow-sidebar" style={{ width: 200, padding: 12 }}>
          <div className="flow-sidebar-label">Palette</div>
          <p style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 10 }}>Drag onto canvas</p>
          {PALETTE.map((p) => (
            <div
              key={p.type}
              draggable
              onDragStart={(e) => onDragStart(e, p.type)}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px',
                marginBottom: 6, borderRadius: 8, border: '1px solid var(--border)',
                cursor: 'grab', fontSize: 12.5, background: 'var(--bg-panel)',
              }}
            >
              <GripVertical size={12} style={{ opacity: 0.5 }} />
              <p.icon size={14} style={{ color: p.accent }} />
              {p.label}
            </div>
          ))}
        </aside>
        <div className="flow-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={(c) => { onNodesChange(c); setDirty(true) }}
            onEdgesChange={(c) => { onEdgesChange(c); setDirty(true) }}
            onConnect={onConnect}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onNodeClick={(_, node) => setModalNode(node)}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.35}
            maxZoom={1.5}
            proOptions={{ hideAttribution: true }}
            deleteKeyCode={['Backspace', 'Delete']}
          >
            <Background gap={18} size={1} color="rgba(148,163,184,0.15)" />
            <Controls showInteractive={false} />
            <MiniMap nodeStrokeWidth={2} pannable zoomable style={{ background: 'var(--bg-panel)' }} />
          </ReactFlow>
        </div>
        {modalNode && (
          <aside className="flow-inspector">
            <NodeConfigModal node={modalNode} refs={refs} panel onClose={() => setModalNode(null)} onSave={saveNodeData} />
          </aside>
        )}
      </div>
      <div className="flow-footer">Integrations fire when visited. Stop aborts remaining nodes. If / Switch pick one branch. Test is a dry-run (no Salesforce / hooks).</div>

      {tplOpen && (
        <div className="modal-overlay" onClick={() => setTplOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <div className="modal-header"><h3>Save as template</h3><button className="btn btn-sm" type="button" onClick={() => setTplOpen(false)}><X size={14} /></button></div>
            <form onSubmit={saveTemplate}>
              <div className="panel-body">
                <div className="field"><label>Template name</label>
                  <input required value={tplName} onChange={(e) => setTplName(e.target.value)} /></div>
                <div className="field"><label>Description</label>
                  <input value={tplDesc} onChange={(e) => setTplDesc(e.target.value)} /></div>
                <label className="flow-check"><input type="checkbox" checked={tplGlobal} onChange={(e) => setTplGlobal(e.target.checked)} /> Global library (all projects)</label>
                <label className="flow-check"><input type="checkbox" checked={tplPlaceholders} onChange={(e) => setTplPlaceholders(e.target.checked)} /> Replace integration / publish IDs with placeholders</label>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setTplOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={tplSaving}>{tplSaving ? 'Saving…' : 'Save template'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {applyOpen && (
        <div className="modal-overlay" onClick={() => setApplyOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 520 }}>
            <div className="modal-header"><h3>Apply template</h3><button className="btn btn-sm" type="button" onClick={() => setApplyOpen(false)}><X size={14} /></button></div>
            <div className="panel-body">
              {(templates || []).length === 0 && <div className="empty-state">No templates in this project yet</div>}
              {(templates || []).map((t) => (
                <div key={t.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                  <div>
                    <strong>{t.name}</strong>
                    <div className="muted" style={{ fontSize: 12 }}>{t.project_id ? 'Project' : 'Global'} · {(t.graph?.nodes || []).length} nodes</div>
                    {t.description && <div style={{ fontSize: 12.5 }}>{t.description}</div>}
                  </div>
                  <button type="button" className="btn btn-sm btn-primary" onClick={() => applyTemplate(t)}>Apply</button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {testOpen && (
        <div className="modal-overlay" onClick={() => setTestOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 560 }}>
            <div className="modal-header"><h3>Dry run</h3><button className="btn btn-sm" type="button" onClick={() => setTestOpen(false)}><X size={14} /></button></div>
            <form onSubmit={runDryTest}>
              <div className="panel-body">
                <p style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Walks If / Switch / Stop / Schema. Processor, publish, and integrations are logged only — not executed.</p>
                <div className="field"><label>Sample JSON</label>
                  <textarea className="mono" rows={8} value={testJson} onChange={(e) => setTestJson(e.target.value)} /></div>
                {testResult && (
                  <div style={{ fontSize: 12.5 }}>
                    <div style={{ marginBottom: 8, color: testResult.ok === false ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                      {testResult.error || 'Dry run — no side effects'}
                    </div>
                    <ol style={{ margin: 0, paddingLeft: 18 }}>
                      {(testResult.steps || []).map((s, i) => (
                        <li key={i} style={{ marginBottom: 4 }}>
                          <strong>{s.label}</strong> · {s.status} — {s.detail}
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setTestOpen(false)}>Close</button>
                <button type="submit" className="btn btn-primary" disabled={testRunning}>{testRunning ? 'Running…' : 'Run test'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default function EventFlowDesigner() {
  const { eventId, pipelineId } = useParams()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [event, setEvent] = useState(null)
  const { projectId } = useProject()
  const [refs, setRefs] = useState({
    rules: [], processors: [], pubs: [], integrations: [], alerts: [],
    spFileActions: [], spListActions: [],
  })

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      try {
        const pid = projectId ? { project_id: projectId } : {}
        const lib = projectId ? { project_id: projectId, include_global: true } : {}
        const [c, r, p, i, a, sf, sl] = await Promise.all([
          api.get('/events', { params: pid }),
          api.get('/rules', { params: lib }),
          api.get('/processors', { params: lib }),
          api.get('/integrations', { params: pid }),
          api.get('/alerts', { params: pid }),
          api.get('/sharepoint/file-actions', { params: pid }).catch(() => ({ data: [] })),
          api.get('/sharepoint/list-actions', { params: pid }).catch(() => ({ data: [] })),
        ])
        if (cancelled) return
        const ev = c.data.find((x) => x.id === eventId)
        if (!ev) { setError('Event channel not found'); return }
        if (ev.direction !== 'subscribe') { setError('Flow designer is only for subscribe channels'); return }
        let graphEvent = ev
        try {
          const pl = await api.get(`/events/${eventId}/pipelines`)
          const list = pl.data || []
          const chosen = list.find((x) => x.id === pipelineId) || list[0]
          if (chosen) {
            graphEvent = { ...ev, flow_graph: chosen.flow_graph || { nodes: [], edges: [] }, _pipelineId: chosen.id, _pipelineName: chosen.name, _pipelines: list }
          }
        } catch (e) { /* fall back to event.flow_graph */ }
        setEvent(graphEvent)
        setRefs({
          rules: r.data || [],
          processors: p.data || [],
          pubs: (c.data || []).filter((x) => x.direction === 'publish' && x.org_id === ev.org_id),
          integrations: i.data || [],
          alerts: a.data || [],
          spFileActions: sf.data || [],
          spListActions: sl.data || [],
        })
      } catch (err) {
        if (!cancelled) setError(err?.response?.data?.detail || err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [eventId, pipelineId, projectId])

  if (loading) return <div className="empty-state">Loading flow…</div>
  if (error && !event) {
    return (
      <div className="panel">
        <div className="empty-state">{error}</div>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <Link to="/events" className="btn">Back to Events</Link>
        </div>
      </div>
    )
  }

  return (
    <ReactFlowProvider>
      <FlowCanvasInner event={event} refs={refs} />
    </ReactFlowProvider>
  )
}
