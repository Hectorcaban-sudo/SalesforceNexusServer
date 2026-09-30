import { CheckCircle2, XCircle, X } from 'lucide-react'
import { useToast } from '../lib/ToastContext'

export default function ToastHost() {
  const { toasts, dismiss } = useToast()
  if (!toasts.length) return null
  return (
    <div className="toast-stack" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast-card toast-${t.kind}`}>
          <div className="toast-icon">
            {t.kind === 'error' ? <XCircle size={16} /> : <CheckCircle2 size={16} />}
          </div>
          <div className="toast-body">
            <div className="toast-title">{t.title}</div>
            {t.detail && <div className="toast-detail">{t.detail}</div>}
          </div>
          <button type="button" className="toast-dismiss" onClick={() => dismiss(t.id)} aria-label="Dismiss">
            <X size={13} />
          </button>
        </div>
      ))}
    </div>
  )
}
