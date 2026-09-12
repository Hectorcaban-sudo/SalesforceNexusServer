import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import api from './api'

const ProjectContext = createContext({
  projects: [],
  projectId: null,
  project: null,
  setProjectId: () => {},
  reload: async () => {},
  loading: true,
})

const STORAGE_KEY = 'nexus_active_project_id'

export function ProjectProvider({ children }) {
  const [projects, setProjects] = useState([])
  const [projectId, setProjectIdState] = useState(() => localStorage.getItem(STORAGE_KEY) || null)
  const [loading, setLoading] = useState(true)

  const reload = useCallback(async () => {
    try {
      const { data } = await api.get('/projects')
      setProjects(data || [])
      setProjectIdState((prev) => {
        if (prev && data.some((p) => p.id === prev)) return prev
        const def = data.find((p) => p.name === 'Default Project') || data[0]
        const next = def?.id || null
        if (next) localStorage.setItem(STORAGE_KEY, next)
        return next
      })
    } catch {
      setProjects([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  function setProjectId(id) {
    setProjectIdState(id)
    if (id) localStorage.setItem(STORAGE_KEY, id)
    else localStorage.removeItem(STORAGE_KEY)
  }

  const project = projects.find((p) => p.id === projectId) || null

  return (
    <ProjectContext.Provider value={{ projects, projectId, project, setProjectId, reload, loading }}>
      {children}
    </ProjectContext.Provider>
  )
}

export function useProject() {
  return useContext(ProjectContext)
}

/** No project_id (or empty) = global library resource. */
export function isGlobalResource(row) {
  const pid = row?.project_id
  return pid == null || pid === ''
}

/**
 * Project-owned rows (orgs, events, integrations, sharepoint).
 * Unscoped legacy rows only appear under Default Project.
 */
export function belongsToProject(row, projectId, project) {
  if (!projectId) return true
  const pid = row?.project_id
  if (pid && pid === projectId) return true
  if (isGlobalResource(row) && project?.name === 'Default Project') return true
  return false
}

/**
 * Processors / rules: project-owned + optional globals (shared library).
 */
export function visibleLibraryItem(row, projectId, { includeGlobal = true } = {}) {
  if (!projectId) return true
  const pid = row?.project_id
  if (pid && pid === projectId) return true
  if (includeGlobal && isGlobalResource(row)) return true
  return false
}
