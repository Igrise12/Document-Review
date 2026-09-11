const rawApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim()

if (!rawApiBaseUrl) {
  throw new Error('VITE_API_BASE_URL is required to start Invoice Review.')
}

let apiBaseUrl: string
try {
  const parsed = new URL(rawApiBaseUrl)
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('unsupported protocol')
  }
  apiBaseUrl = parsed.toString().replace(/\/$/, '')
} catch {
  throw new Error('VITE_API_BASE_URL must be a valid HTTP or HTTPS URL.')
}

export const env = { apiBaseUrl } as const
