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

/** Row belongs to active project (or unscoped rows visible only on Default Project). */
export function belongsToProject(row, projectId, project) {
  if (!projectId) return true
  const pid = row?.project_id
  if (pid === projectId) return true
  // Legacy rows without project_id show under Default Project only
  if (!pid && project?.name === 'Default Project') return true
  return false
}
