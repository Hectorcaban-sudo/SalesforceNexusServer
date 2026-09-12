import { useEffect, useRef, useState } from 'react'
import { FolderKanban, Check, ChevronDown } from 'lucide-react'
import { useProject } from '../lib/ProjectContext'

function initials(name) {
  if (!name) return 'P'
  const parts = String(name).trim().split(/\s+/).filter(Boolean)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

const ACCENTS = ['#6366f1', '#0ea5e9', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6']

function accentFor(id) {
  if (!id) return ACCENTS[0]
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0
  return ACCENTS[h % ACCENTS.length]
}

export default function ProjectSwitcher() {
  const { projects, projectId, project, setProjectId } = useProject()
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  useEffect(() => {
    function onDoc(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false)
    }
    function onKey(e) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [])

  const sorted = [...(projects || [])].sort((a, b) => (a.name || '').localeCompare(b.name || ''))

  return (
    <div className="project-switcher" ref={rootRef}>
      <button
        type="button"
        className="project-switcher-trigger"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        <span
          className="project-switcher-avatar"
          style={{ background: accentFor(project?.id) }}
        >
          {initials(project?.name)}
        </span>
        <span className="project-switcher-text">
          <span className="project-switcher-label">Project</span>
          <span className="project-switcher-name">{project?.name || 'Select project'}</span>
        </span>
        <ChevronDown size={14} className={'project-switcher-chevron' + (open ? ' open' : '')} />
      </button>

      {open && (
        <div className="project-switcher-menu" role="listbox">
          <div className="project-switcher-menu-header">
            <FolderKanban size={14} />
            Switch project
          </div>
          <ul className="project-switcher-list">
            {sorted.map((p) => {
              const selected = p.id === projectId
              return (
                <li key={p.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={selected}
                    className={'project-switcher-item' + (selected ? ' selected' : '')}
                    onClick={() => {
                      setProjectId(p.id)
                      setOpen(false)
                    }}
                  >
                    <span
                      className="project-switcher-avatar sm"
                      style={{ background: accentFor(p.id) }}
                    >
                      {initials(p.name)}
                    </span>
                    <span className="project-switcher-item-text">
                      <span className="project-switcher-item-name">{p.name}</span>
                      <span className="project-switcher-item-sub">
                        {p.description ? p.description : (p.enabled === false ? 'Disabled' : 'Active workspace')}
                      </span>
                    </span>
                    {selected && <Check size={15} className="project-switcher-check" />}
                  </button>
                </li>
              )
            })}
            {sorted.length === 0 && (
              <li className="project-switcher-empty">No projects yet</li>
            )}
          </ul>
        </div>
      )}
    </div>
  )
}
