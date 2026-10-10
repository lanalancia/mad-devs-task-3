const backendAddress = __BACKEND_ADDRESS__.replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, { code = '', status = 0 } = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

export async function api(path, { method = 'GET', token = '', body, timeoutMs = 5000 } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  let response
  try {
    response = await fetch(`${backendAddress}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    })
  } catch (error) {
    if (error?.name === 'TimeoutError' || error?.name === 'AbortError') {
      throw new ApiError('The request timed out.')
    }
    throw new ApiError('Failed to reach the backend.')
  }
  const text = await response.text()
  let payload = {}
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      throw new ApiError('The backend returned an unexpected response.')
    }
  }
  if (response.status === 401 && payload.error === 'token_expired') {
    throw new ApiError('Please sign in again', { code: 'token_expired', status: 401 })
  }
  if (!response.ok) {
    const message = typeof payload.error === 'string' && payload.error ? payload.error : 'Request failed.'
    throw new ApiError(message, { status: response.status })
  }
  return payload
}
