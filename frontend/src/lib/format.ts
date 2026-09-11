import type { CurrencyCode } from '@/lib/types'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

export function formatDate(value: string | null): string {
  if (!value) return 'Not provided'
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium' }).format(date)
}

export function formatDateTime(value: string | null): string {
  if (!value) return 'Not processed'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export function formatMoney(value: string | null, currency: CurrencyCode | string | null): string {
  if (value === null || value === '') return 'Not provided'
  const code = typeof currency === 'string' ? currency : currency?.code
  const numeric = Number(value)
  if (!code || Number.isNaN(numeric)) return code ? `${code} ${value}` : value
  return new Intl.NumberFormat('en-IE', {
    style: 'currency',
    currency: code,
    minimumFractionDigits: 2,
  }).format(numeric)
}

export function formatEvidenceValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Not provided'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  if (isRecord(value)) {
    const display = value.display
    if (typeof display === 'string') return display
    const code = value.code
    if (typeof code === 'string') return code
  }
  return 'Structured value available'
}

export function fieldLabel(field: string): string {
  return field.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}
