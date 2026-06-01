const API_BASE_URL = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL)

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }

  get isNotFound() {
    return this.status === 404
  }
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    throw new ApiError(`Request failed: ${response.status}`, response.status)
  }

  return response.json() as Promise<T>
}

function buildApiUrl(path: string) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${normalizedPath}`
}

function normalizeBaseUrl(value: string | undefined) {
  if (!value) return ''
  return value.endsWith('/') ? value.slice(0, -1) : value
}
