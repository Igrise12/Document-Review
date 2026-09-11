type LogLevel = 'info' | 'warn' | 'error'
type SafeLogValue = boolean | null | number | string
type SafeLogContext = Readonly<Record<string, SafeLogValue>>

/**
 * Console-only operational events. Context must never include document data,
 * filenames, review values, object URLs, drafts, or provider credentials.
 */
export function logFrontendEvent(
  level: LogLevel,
  event: string,
  context: SafeLogContext = {},
) {
  const payload = { event, at: new Date().toISOString(), ...context }
  const method = level === 'error' ? console.error : level === 'warn' ? console.warn : console.info
  method('[invoice-review]', payload)
}
