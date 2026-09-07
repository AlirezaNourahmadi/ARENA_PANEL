function cookie(name) {
  const item = document.cookie
    .split('; ')
    .find((part) => part.startsWith(`${name}=`))
  return item ? decodeURIComponent(item.split('=').slice(1).join('=')) : ''
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {})
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const csrf = cookie('arena_csrf')
  if (csrf) headers.set('X-CSRF-Token', csrf)
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...options,
    headers,
  })
  if (!response.ok) {
    let message = `خطای ${response.status}`
    try {
      const payload = await response.json()
      message = payload.detail || message
    } catch {
      message = (await response.text()) || message
    }
    const error = new Error(message)
    error.status = response.status
    throw error
  }
  const type = response.headers.get('content-type') || ''
  return type.includes('application/json') ? response.json() : response.text()
}

export const api = {
  session: () => request('/api/auth/session'),
  login: (payload) => request('/api/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  dashboard: () => request('/api/dashboard'),
  health: () => request('/api/health'),
  users: () => request('/api/users'),
  user: (id) => request(`/api/users/${id}`),
  createUser: (payload) => request('/api/users', { method: 'POST', body: JSON.stringify(payload) }),
  updateUser: (id, payload) => request(`/api/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteUser: (id) => request(`/api/users/${id}`, { method: 'DELETE' }),
  resetUsage: (id) => request(`/api/users/${id}/reset-usage`, { method: 'POST' }),
  rotateSubscription: (id) => request(`/api/users/${id}/rotate-subscription`, { method: 'POST' }),
  formats: (id) => request(`/api/users/${id}/formats`),
  attachNode: (userId, nodeId) => request(`/api/users/${userId}/nodes/${nodeId}`, { method: 'POST' }),
  detachNode: (userId, nodeId) => request(`/api/users/${userId}/nodes/${nodeId}`, { method: 'DELETE' }),
  nodes: () => request('/api/nodes'),
  createNode: (payload) => request('/api/nodes', { method: 'POST', body: JSON.stringify(payload) }),
  updateNode: (id, payload) => request(`/api/nodes/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  logs: (userId = '') => request(`/api/logs${userId ? `?user_id=${encodeURIComponent(userId)}` : ''}`),
}
