import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

export default function SsoCallback() {
  const [params] = useSearchParams()
  const navigate = useNavigate()

  useEffect(() => {
    const token = params.get('token')
    if (token) {
      localStorage.setItem('nexus_token', token)
      navigate('/', { replace: true })
    } else {
      navigate('/login', { replace: true })
    }
  }, [params, navigate])

  return (
    <div className="login-screen">
      <div className="panel login-card" style={{ textAlign: 'center' }}>
        <div className="login-logo">
          <div className="mark">SN</div>
          <h2>Signing you in…</h2>
          <p>Completing single sign-on</p>
        </div>
      </div>
    </div>
  )
}
