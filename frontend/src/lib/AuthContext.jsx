import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import api from './api'

const AuthContext = createContext({ user: null, loading: true, refresh: () => {} })

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(() => {
    setLoading(true)
    return api.get('/auth/me')
      .then((r) => setUser(r.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { refresh() }, [refresh])

  return <AuthContext.Provider value={{ user, loading, refresh }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}

const ROLE_RANK = { viewer: 0, operator: 1, admin: 2 }

export function hasRole(user, minRole) {
  if (!user) return false
  return (ROLE_RANK[user.role] ?? -1) >= (ROLE_RANK[minRole] ?? 99)
}
