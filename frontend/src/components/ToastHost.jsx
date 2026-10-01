import { createPortal } from 'react-dom'
import { CheckCircle2, XCircle, X } from 'lucide-react'
import { useToast } from '../lib/ToastContext'

const stackStyle = {
  position: 'fixed',
  right: 20,
  bottom: 20,
  zIndex: 2147483647,
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
  width: 'min(360px, calc(100vw - 32px))',
  pointerEvents: 'none',
}

function cardStyle(kind) {
  return {
    pointerEvents: 'auto',
    display: 'flex',
    gap: 10,
    alignItems: 'flex-start',
    padding: '10px 12px',
    background: '#12161c',
    color: '#e8eef3',
    border: '1px solid rgba(183,196,208,0.25)',
    borderLeft: kind === 'error' ? '3px solid #c45c5c' : '3px solid #7eb6d6',
    borderRadius: 8,
    boxShadow: '0 8px 24px rgba(0,0,0,0.45)',
  }
}

export default function ToastHost() {
  const { toasts, dismiss } = useToast()
  if (typeof document === 'undefined' || !toasts.length) return null
  return createPortal(
    <div style={stackStyle} aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} style={cardStyle(t.kind)}>
          <div style={{ color: t.kind === 'error' ? '#c45c5c' : '#7eb6d6', marginTop: 1 }}>
            {t.kind === 'error' ? <XCircle size={16} /> : <CheckCircle2 size={16} />}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{t.title}</div>
            {t.detail && <div style={{ fontSize: 12, color: '#b7c4d0', marginTop: 2 }}>{t.detail}</div>}
          </div>
          <button type="button" onClick={() => dismiss(t.id)} aria-label="Dismiss" style={{ background: 'transparent', border: 0, color: '#b7c4d0', cursor: 'pointer' }}>
            <X size={13} />
          </button>
        </div>
      ))}
    </div>,
    document.body,
  )
}
