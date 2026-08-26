import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('nexus_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401) {
      localStorage.removeItem('nexus_token')
      if (!location.pathname.includes('/login')) {
        window.dispatchEvent(new Event('nexus:unauthorized'))
      }
    }
    return Promise.reject(err)
  }
)

export async function login(username, password) {
  const form = new URLSearchParams()
  form.set('username', username)
  form.set('password', password)
  const { data } = await axios.post('/api/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  localStorage.setItem('nexus_token', data.access_token)
  return data
}

export function logout() {
  localStorage.removeItem('nexus_token')
}

export function isAuthed() {
  return !!localStorage.getItem('nexus_token')
}

export default api
