import { env } from './env'

export type HealthResponse = {
  status: 'ok'
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${env.apiBaseUrl}/health`, {
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!response.ok) {
    throw new Error(`Backend returned HTTP ${response.status}.`)
  }

  const body: unknown = await response.json()
  if (!isHealthResponse(body)) {
    throw new Error('Backend returned an invalid health response.')
  }
  return body
}

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== 'object' || value === null || !('status' in value)) {
    return false
  }
  return Reflect.get(value, 'status') === 'ok'
}
