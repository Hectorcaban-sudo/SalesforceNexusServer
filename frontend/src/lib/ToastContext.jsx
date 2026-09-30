import { createContext, useCallback, useContext, useState } from 'react'

const ToastContext = createContext({ toast: () => {}, dismiss: () => {}, toasts: [] })

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismiss = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id))
  }, [])

  const toast = useCallback((title, opts = {}) => {
    const id = Math.random().toString(36).slice(2, 10)
    const kind = opts.kind === 'error' ? 'error' : 'ok'
    const item = { id, title: String(title || ''), detail: opts.detail ? String(opts.detail) : '', kind }
    setToasts((list) => [...list.slice(-2), item])
    if (kind !== 'error') {
      setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), opts.ms || 3500)
    }
  }, [])

  return (
    <ToastContext.Provider value={{ toast, dismiss, toasts }}>
      {children}
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
