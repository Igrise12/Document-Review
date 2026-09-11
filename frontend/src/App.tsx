import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { getHealth } from './lib/api'

const MAX_UPLOAD_BYTES = 4 * 1024 * 1024
const ACCEPTED_MIME_TYPES = new Set(['application/pdf', 'image/png', 'image/jpeg'])
const ACCEPTED_EXTENSIONS = new Set(['pdf', 'png', 'jpg', 'jpeg'])

type HealthState = 'checking' | 'healthy' | 'unavailable'
type PreviewKind = 'pdf' | 'image'
type SelectedFile = { file: File; kind: PreviewKind; previewUrl: string }

function fileKind(file: File): PreviewKind | null {
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (file.type === 'application/pdf' || extension === 'pdf') return 'pdf'
  if (file.type.startsWith('image/') && ACCEPTED_MIME_TYPES.has(file.type)) return 'image'
  if (extension && ACCEPTED_EXTENSIONS.has(extension)) {
    return extension === 'pdf' ? 'pdf' : 'image'
  }
  return null
}

function validateFile(file: File): string | null {
  if (file.size > MAX_UPLOAD_BYTES) return 'File is larger than the 4 MB checkpoint limit.'
  if (!fileKind(file)) return 'Choose one PDF, PNG, or JPEG document.'
  if (file.type && !ACCEPTED_MIME_TYPES.has(file.type)) {
    return 'The file media type must be PDF, PNG, or JPEG.'
  }
  return null
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function App() {
  const [healthState, setHealthState] = useState<HealthState>('checking')
  const [healthMessage, setHealthMessage] = useState('Checking the local backend…')
  const [selectedFile, setSelectedFile] = useState<SelectedFile | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const healthController = useRef<AbortController | null>(null)

  const checkHealth = useCallback(() => {
    healthController.current?.abort()
    const controller = new AbortController()
    healthController.current = controller
    setHealthState('checking')
    setHealthMessage('Checking the local backend…')

    void getHealth(controller.signal)
      .then(() => {
        if (controller.signal.aborted) return
        setHealthState('healthy')
        setHealthMessage('Backend is healthy and ready for the next API stage.')
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        const message = error instanceof Error ? error.message : 'The backend could not be reached.'
        setHealthState('unavailable')
        setHealthMessage(message)
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    healthController.current = controller
    void getHealth(controller.signal)
      .then(() => {
        if (controller.signal.aborted) return
        setHealthState('healthy')
        setHealthMessage('Backend is healthy and ready for the next API stage.')
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        const message = error instanceof Error ? error.message : 'The backend could not be reached.'
        setHealthState('unavailable')
        setHealthMessage(message)
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    return () => {
      if (selectedFile) URL.revokeObjectURL(selectedFile.previewUrl)
    }
  }, [selectedFile])

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    const error = validateFile(file)
    if (error) {
      setFileError(error)
      setSelectedFile(null)
      event.target.value = ''
      return
    }

    setFileError(null)
    setSelectedFile({
      file,
      kind: fileKind(file) ?? 'image',
      previewUrl: URL.createObjectURL(file),
    })
    event.target.value = ''
  }

  const removeFile = () => {
    setSelectedFile(null)
    setFileError(null)
  }

  const healthLabel = healthState === 'checking'
    ? 'Checking'
    : healthState === 'healthy'
      ? 'Healthy'
      : 'Unavailable'

  return (
    <div className="app-frame">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Invoice Review home">
          <span className="brand-mark" aria-hidden="true">IR</span>
          <span>Invoice Review</span>
        </a>
        <span className="environment-tag">Developer harness</span>
      </header>

      <main className="workspace">
        <section className="intro-row" aria-labelledby="page-title">
          <div>
            <p className="section-label">Stage 4</p>
            <h1 id="page-title">Primary Parser Checkpoint</h1>
            <p className="intro-copy">
              Confirm the local review surface before upload and processing APIs arrive.
            </p>
          </div>
          <div className={`health-badge health-${healthState}`}>
            <span className="health-dot" aria-hidden="true" />
            <span>{healthLabel}</span>
          </div>
        </section>

        <section className="progress-strip" aria-label="Pipeline progress">
          <div className="stage-item stage-complete">
            <span className="stage-number">01</span>
            <span><strong>Contracts</strong><small>Complete</small></span>
          </div>
          <div className="stage-item stage-complete">
            <span className="stage-number">02</span>
            <span><strong>Persistence</strong><small>Complete</small></span>
          </div>
          <div className="stage-item stage-current">
            <span className="stage-number">03</span>
            <span><strong>Primary parser</strong><small>Current checkpoint</small></span>
          </div>
          <div className="stage-item stage-next">
            <span className="stage-number">04</span>
            <span><strong>VLM review</strong><small>Next</small></span>
          </div>
        </section>

        <section className="health-panel" aria-labelledby="health-title">
          <div>
            <p className="panel-label">Backend status</p>
            <h2 id="health-title">Local API connection</h2>
            <p className="status-copy" aria-live="polite">{healthMessage}</p>
          </div>
          {healthState === 'unavailable' && (
            <button className="button button-secondary" type="button" onClick={checkHealth}>
              Retry health
            </button>
          )}
        </section>

        <section className="checkpoint-grid" aria-label="Document checkpoint">
          <div className="control-column">
            <div className="upload-panel">
              <div className="panel-heading">
                <div>
                  <p className="panel-label">Input document</p>
                  <h2>Select one document</h2>
                </div>
                <span className="limit-note">4 MB max</span>
              </div>
              <label className="file-picker" htmlFor="document-input">
                <span className="file-picker-mark" aria-hidden="true">+</span>
                <span>
                  <strong>Choose PDF, PNG, or JPEG</strong>
                  <small>Selection stays in this browser for preview only.</small>
                </span>
              </label>
              <input
                id="document-input"
                className="visually-hidden"
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                onChange={handleFileChange}
              />
              <p className="validation-message" aria-live="polite">
                {fileError ?? 'Supported formats: PDF, PNG, JPEG.'}
              </p>

              {selectedFile && (
                <div className="file-details">
                  <div>
                    <p className="file-name">{selectedFile.file.name}</p>
                    <p className="file-meta">
                      {formatBytes(selectedFile.file.size)} / {selectedFile.file.type || 'type inferred from extension'}
                    </p>
                  </div>
                  <button className="text-button" type="button" onClick={removeFile}>
                    Remove
                  </button>
                </div>
              )}
            </div>

            <div className="processing-note">
              <p className="panel-label">API boundary</p>
              <h2>Processing is not available yet</h2>
              <p>
                This checkpoint verifies health, file validation, and local preview. No extraction,
                confidence, or approval result is simulated here.
              </p>
            </div>
          </div>

          <div className="preview-panel">
            <div className="preview-heading">
              <div>
                <p className="panel-label">Document preview</p>
                <h2>{selectedFile ? selectedFile.file.name : 'Preview area'}</h2>
              </div>
              <span className="preview-state">{selectedFile ? 'Local file' : 'Waiting for file'}</span>
            </div>
            <div className={`preview-canvas ${selectedFile ? 'preview-filled' : ''}`}>
              {selectedFile?.kind === 'image' && (
                <img src={selectedFile.previewUrl} alt={`Preview of ${selectedFile.file.name}`} />
              )}
              {selectedFile?.kind === 'pdf' && (
                <iframe title={`Preview of ${selectedFile.file.name}`} src={selectedFile.previewUrl} />
              )}
              {!selectedFile && (
                <div className="preview-empty">
                  <span className="empty-sheet" aria-hidden="true" />
                  <p>Choose a document to inspect it here.</p>
                  <small>The preview never calls the parser.</small>
                </div>
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}

export default App
