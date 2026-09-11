import { env } from '@/lib/env'
import { logFrontendEvent } from '@/lib/logger'
import type {
  CorrectionDraftResult,
  GLAccount,
  ReviewDetail,
  ReviewState,
  ReviewSummary,
} from '@/lib/types'

export type HealthResponse = { status: 'ok' }

export class ApiClientError extends Error {
  readonly status: number | null
  readonly code: string | null

  constructor(message: string, status: number | null, code: string | null) {
    super(message)
    this.name = 'ApiClientError'
    this.status = status
    this.code = code
  }
}

type JsonRequest = RequestInit & { method: 'DELETE' | 'GET' | 'POST' | 'PUT' }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isReviewState(value: unknown): value is ReviewState {
  return typeof value === 'string' && [
    'uploaded',
    'processing',
    'ready_for_review',
    'approved',
    'rejected',
    'correction_requested',
    'failed',
  ].includes(value)
}

function isHealthResponse(value: unknown): value is HealthResponse {
  return isRecord(value) && value.status === 'ok'
}

function isReviewDetail(value: unknown): value is ReviewDetail {
  return (
    isRecord(value)
    && typeof value.review_id === 'string'
    && isReviewState(value.state)
    && isRecord(value.original_file)
    && isRecord(value.evidence)
    && isRecord(value.conflicts)
    && Array.isArray(value.issues)
    && typeof value.approval_allowed === 'boolean'
  )
}

function isReviewSummary(value: unknown): value is ReviewSummary {
  return isRecord(value) && typeof value.review_id === 'string' && isReviewState(value.state)
}

function isGLAccount(value: unknown): value is GLAccount {
  return (
    isRecord(value)
    && typeof value.account_id === 'string'
    && typeof value.label === 'string'
    && typeof value.category === 'string'
  )
}

function isCorrectionDraftResult(value: unknown): value is CorrectionDraftResult {
  return isRecord(value) && isRecord(value.draft) && typeof value.draft.text === 'string'
}

async function errorFrom(response: Response): Promise<ApiClientError> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // A handled API error is expected to be JSON, but the client still gives a useful message.
  }
  if (isRecord(body) && isRecord(body.error)) {
    const message = body.error.message
    const code = body.error.code
    if (typeof message === 'string') {
      return new ApiClientError(
        message,
        response.status,
        typeof code === 'string' ? code : null,
      )
    }
  }
  return new ApiClientError(`Backend returned HTTP ${response.status}.`, response.status, null)
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

async function requestJson<T>(
  operation: string,
  path: string,
  request: JsonRequest,
  validate: (body: unknown) => body is T,
): Promise<T> {
  const startedAt = performance.now()
  let status: number | null = null
  try {
    const response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...request,
      headers: { Accept: 'application/json', ...request.headers },
    })
    status = response.status
    if (!response.ok) throw await errorFrom(response)
    const body: unknown = await response.json()
    if (!validate(body)) {
      throw new ApiClientError('Backend returned an invalid response.', status, 'invalid_response')
    }
    logFrontendEvent('info', 'api.request_completed', {
      operation,
      method: request.method,
      status,
      durationMs: Math.round(performance.now() - startedAt),
      outcome: 'success',
    })
    return body
  } catch (error: unknown) {
    if (isAbortError(error)) throw error
    logFrontendEvent('error', 'api.request_failed', {
      operation,
      method: request.method,
      status: status ?? 0,
      apiCode: error instanceof ApiClientError ? error.code ?? 'unknown' : 'network_error',
      durationMs: Math.round(performance.now() - startedAt),
      outcome: 'failure',
    })
    throw error
  }
}

async function requestEmpty(operation: string, path: string, request: JsonRequest): Promise<void> {
  const startedAt = performance.now()
  let status: number | null = null
  try {
    const response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...request,
      headers: { Accept: 'application/json', ...request.headers },
    })
    status = response.status
    if (!response.ok) throw await errorFrom(response)
    logFrontendEvent('info', 'api.request_completed', {
      operation,
      method: request.method,
      status,
      durationMs: Math.round(performance.now() - startedAt),
      outcome: 'success',
    })
  } catch (error: unknown) {
    if (isAbortError(error)) throw error
    logFrontendEvent('error', 'api.request_failed', {
      operation,
      method: request.method,
      status: status ?? 0,
      apiCode: error instanceof ApiClientError ? error.code ?? 'unknown' : 'network_error',
      durationMs: Math.round(performance.now() - startedAt),
      outcome: 'failure',
    })
    throw error
  }
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return requestJson('health_check', '/health', { method: 'GET', signal }, isHealthResponse)
}

export function listReviews(): Promise<ReviewSummary[]> {
  return requestJson('list_reviews', '/reviews', { method: 'GET' }, (body): body is ReviewSummary[] => (
    Array.isArray(body) && body.every(isReviewSummary)
  ))
}

export function getReview(reviewId: string): Promise<ReviewDetail> {
  return requestJson('get_review', `/reviews/${encodeURIComponent(reviewId)}`, { method: 'GET' }, isReviewDetail)
}

export function getGlCatalog(): Promise<GLAccount[]> {
  return requestJson('get_gl_catalog', '/gl-catalog', { method: 'GET' }, (body): body is GLAccount[] => (
    Array.isArray(body) && body.every(isGLAccount)
  ))
}

export function uploadReview(file: File): Promise<ReviewDetail> {
  const body = new FormData()
  body.append('file', file)
  return requestJson('upload_review', '/reviews', { method: 'POST', body }, isReviewDetail)
}

export function processReview(reviewId: string): Promise<ReviewDetail> {
  return requestJson(
    'process_review',
    `/reviews/${encodeURIComponent(reviewId)}/process`,
    { method: 'POST' },
    isReviewDetail,
  )
}

export function selectGl(reviewId: string, accountId: string | null): Promise<ReviewDetail> {
  return requestJson(
    'select_gl',
    `/reviews/${encodeURIComponent(reviewId)}/gl-selection`,
    {
      method: 'PUT',
      body: JSON.stringify({ account_id: accountId }),
      headers: { 'Content-Type': 'application/json' },
    },
    isReviewDetail,
  )
}

export function approveReview(reviewId: string): Promise<ReviewDetail> {
  return requestJson(
    'approve_review',
    `/reviews/${encodeURIComponent(reviewId)}/approve`,
    { method: 'POST' },
    isReviewDetail,
  )
}

export function rejectReview(reviewId: string): Promise<ReviewDetail> {
  return requestJson(
    'reject_review',
    `/reviews/${encodeURIComponent(reviewId)}/reject`,
    { method: 'POST' },
    isReviewDetail,
  )
}

export function requestCorrection(reviewId: string): Promise<ReviewDetail> {
  return requestJson(
    'request_correction',
    `/reviews/${encodeURIComponent(reviewId)}/correction-request`,
    { method: 'POST' },
    isReviewDetail,
  )
}

export function generateCorrectionDraft(reviewId: string): Promise<CorrectionDraftResult> {
  return requestJson(
    'generate_correction_draft',
    `/reviews/${encodeURIComponent(reviewId)}/correction-draft`,
    { method: 'POST' },
    isCorrectionDraftResult,
  )
}

export function deleteReview(reviewId: string): Promise<void> {
  return requestEmpty('delete_review', `/reviews/${encodeURIComponent(reviewId)}`, { method: 'DELETE' })
}

export async function getOriginal(reviewId: string): Promise<Blob> {
  const startedAt = performance.now()
  let status: number | null = null
  try {
    const response = await fetch(`${env.apiBaseUrl}/reviews/${encodeURIComponent(reviewId)}/original`, {
      headers: { Accept: 'application/pdf,image/png,image/jpeg' },
    })
    status = response.status
    if (!response.ok) throw await errorFrom(response)
    const body = await response.blob()
    logFrontendEvent('info', 'api.request_completed', {
      operation: 'get_original',
      method: 'GET',
      status,
      durationMs: Math.round(performance.now() - startedAt),
      outcome: 'success',
    })
    return body
  } catch (error: unknown) {
    logFrontendEvent('error', 'api.request_failed', {
      operation: 'get_original',
      method: 'GET',
      status: status ?? 0,
      apiCode: error instanceof ApiClientError ? error.code ?? 'unknown' : 'network_error',
      durationMs: Math.round(performance.now() - startedAt),
      outcome: 'failure',
    })
    throw error
  }
}

export function messageFor(error: unknown, fallback: string): string {
  return error instanceof ApiClientError ? error.message : fallback
}
