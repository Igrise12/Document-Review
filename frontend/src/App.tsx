import { useCallback, useEffect, useState } from 'react'
import type { ChangeEvent } from 'react'
import { Plus, RefreshCw } from 'lucide-react'

import {
  approveReview,
  deleteReview,
  generateCorrectionDraft,
  getGlCatalog,
  getHealth,
  getOriginal,
  getReview,
  listReviews,
  messageFor,
  processReview,
  rejectReview,
  requestCorrection,
  selectGl,
  uploadReview,
} from '@/lib/api'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CorrectionDraftDialog } from '@/components/correction-draft-dialog'
import { DocumentPreview } from '@/components/document-preview'
import { HistoryPanel } from '@/components/history-panel'
import { ReviewPanel } from '@/components/review-panel'
import { UploadPanel } from '@/components/upload-panel'
import { logFrontendEvent } from '@/lib/logger'
import type { GLAccount, ReviewDetail, ReviewSummary } from '@/lib/types'

const MAX_UPLOAD_BYTES = 4 * 1024 * 1024
const ACCEPTED_MIME_TYPES = new Set(['application/pdf', 'image/png', 'image/jpeg'])
const ACCEPTED_EXTENSIONS = new Set(['pdf', 'png', 'jpg', 'jpeg'])

type PreviewKind = 'pdf' | 'image'
type Preview = {
  fileName: string
  mediaType: 'application/pdf' | 'image/png' | 'image/jpeg'
  url: string
}
type HealthState = 'checking' | 'healthy' | 'unavailable'
type BusyAction = 'approve' | 'delete' | 'draft' | 'gl' | 'open' | 'process' | 'reject' | 'request_correction' | 'upload'
type Notice = { message: string; variant: 'default' | 'destructive' }

const PROCESSING_STAGE_COUNT = 5

function fileKind(file: File): PreviewKind | null {
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (file.type === 'application/pdf' || extension === 'pdf') return 'pdf'
  if (file.type.startsWith('image/') && ACCEPTED_MIME_TYPES.has(file.type)) return 'image'
  if (extension && ACCEPTED_EXTENSIONS.has(extension)) return extension === 'pdf' ? 'pdf' : 'image'
  return null
}

function mediaTypeFor(file: File): Preview['mediaType'] {
  if (file.type === 'application/pdf' || fileKind(file) === 'pdf') return 'application/pdf'
  return file.type === 'image/png' || file.name.toLowerCase().endsWith('.png') ? 'image/png' : 'image/jpeg'
}

function validateFile(file: File): string | null {
  if (file.size > MAX_UPLOAD_BYTES) return 'File is larger than the 4 MB limit.'
  if (!fileKind(file)) return 'Choose one PDF, PNG, or JPEG document.'
  if (file.type && !ACCEPTED_MIME_TYPES.has(file.type)) return 'The file media type must be PDF, PNG, or JPEG.'
  return null
}

function App() {
  const [healthState, setHealthState] = useState<HealthState>('checking')
  const [healthMessage, setHealthMessage] = useState('Checking the local backend…')
  const [history, setHistory] = useState<ReviewSummary[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [accounts, setAccounts] = useState<GLAccount[]>([])
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [review, setReview] = useState<ReviewDetail | null>(null)
  const [busyAction, setBusyAction] = useState<BusyAction | null>(null)
  const [processingStage, setProcessingStage] = useState(0)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [draftOpen, setDraftOpen] = useState(false)
  const [draft, setDraft] = useState<string | null>(null)
  const [draftError, setDraftError] = useState<string | null>(null)
  const [copyMessage, setCopyMessage] = useState<string | null>(null)
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)

  const busy = busyAction !== null

  useEffect(() => {
    if (busyAction !== 'process') return

    const timer = window.setInterval(() => {
      setProcessingStage((stage) => Math.min(stage + 1, PROCESSING_STAGE_COUNT - 1))
    }, 5000)

    return () => window.clearInterval(timer)
  }, [busyAction])

  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      setHistory(await listReviews())
    } catch (error: unknown) {
      setNotice({ message: messageFor(error, 'Could not load local review history.'), variant: 'destructive' })
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  const checkHealth = useCallback(async (signal?: AbortSignal) => {
    setHealthState('checking')
    setHealthMessage('Checking the local backend…')
    try {
      await getHealth(signal)
      setHealthState('healthy')
      setHealthMessage('Local API is ready.')
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      setHealthState('unavailable')
      setHealthMessage(messageFor(error, 'The local backend could not be reached.'))
    }
  }, [])

  const loadCatalog = useCallback(async () => {
    try {
      setAccounts(await getGlCatalog())
    } catch (error: unknown) {
      setNotice({ message: messageFor(error, 'Could not load the Northstar GL catalog.'), variant: 'destructive' })
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const startRequests = window.setTimeout(() => {
      void checkHealth(controller.signal)
      void refreshHistory()
      void loadCatalog()
    }, 0)
    return () => {
      controller.abort()
      window.clearTimeout(startRequests)
    }
  }, [checkHealth, loadCatalog, refreshHistory])

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview.url)
  }, [preview])

  const resetToWelcome = () => {
    setSelectedFile(null)
    setPreview(null)
    setFileError(null)
    setReview(null)
    setDraft(null)
    setDraftError(null)
    setCopyMessage(null)
    setNotice(null)
  }

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    const error = validateFile(file)
    if (error) {
      setSelectedFile(null)
      setPreview(null)
      setFileError(error)
      logFrontendEvent('warn', 'upload.validation_failed', { reason: error.includes('4 MB') ? 'size_limit' : 'unsupported_file' })
      return
    }

    setReview(null)
    setDraft(null)
    setDraftError(null)
    setCopyMessage(null)
    setFileError(null)
    setSelectedFile(file)
    setPreview({ fileName: file.name, mediaType: mediaTypeFor(file), url: URL.createObjectURL(file) })
    logFrontendEvent('info', 'upload.file_selected', { mediaType: mediaTypeFor(file) })
  }

  const handleRemoveFile = () => {
    setSelectedFile(null)
    setPreview(null)
    setFileError(null)
    logFrontendEvent('info', 'upload.file_removed')
  }

  const handleUpload = async () => {
    if (!selectedFile) return
    setBusyAction('upload')
    setNotice(null)
    logFrontendEvent('info', 'review.action_started', { action: 'upload' })
    try {
      const uploaded = await uploadReview(selectedFile)
      setReview(uploaded)
      setNotice({ message: 'Document uploaded. Start processing when you are ready.', variant: 'default' })
      logFrontendEvent('info', 'review.action_completed', { action: 'upload', state: uploaded.state })
      await refreshHistory()
    } catch (error: unknown) {
      setNotice({ message: messageFor(error, 'Could not upload the document.'), variant: 'destructive' })
      logFrontendEvent('error', 'review.action_failed', { action: 'upload' })
    } finally {
      setBusyAction(null)
    }
  }

  const handleOpenReview = async (reviewId: string) => {
    setBusyAction('open')
    setNotice(null)
    logFrontendEvent('info', 'review.action_started', { action: 'open' })
    try {
      const [detail, original] = await Promise.all([getReview(reviewId), getOriginal(reviewId)])
      setReview(detail)
      setSelectedFile(null)
      setPreview({
        fileName: detail.original_file.filename,
        mediaType: detail.original_file.media_type,
        url: URL.createObjectURL(original),
      })
      setDraft(null)
      setDraftError(null)
      setCopyMessage(null)
      logFrontendEvent('info', 'review.action_completed', { action: 'open', state: detail.state })
    } catch (error: unknown) {
      setNotice({ message: messageFor(error, 'Could not open that review.'), variant: 'destructive' })
      logFrontendEvent('error', 'review.action_failed', { action: 'open' })
    } finally {
      setBusyAction(null)
    }
  }

  const updateReview = async (
    action: Exclude<BusyAction, 'delete' | 'open' | 'upload'>,
    operation: () => Promise<ReviewDetail>,
    successMessage: string,
  ) => {
    if (action === 'process') setProcessingStage(0)
    setBusyAction(action)
    setNotice(null)
    logFrontendEvent('info', 'review.action_started', { action })
    try {
      const updated = await operation()
      setReview(updated)
      const failed = updated.state === 'failed'
      setNotice({ message: failed ? updated.failure_message ?? 'Processing failed. You can retry it.' : successMessage, variant: failed ? 'destructive' : 'default' })
      logFrontendEvent('info', 'review.action_completed', { action, state: updated.state })
      await refreshHistory()
    } catch (error: unknown) {
      setNotice({ message: messageFor(error, 'Could not update the review.'), variant: 'destructive' })
      logFrontendEvent('error', 'review.action_failed', { action })
    } finally {
      if (action === 'process') setProcessingStage(0)
      setBusyAction(null)
    }
  }

  const handleProcess = () => {
    if (!review) return
    void updateReview('process', () => processReview(review.review_id), 'Review is ready for Maya to inspect.')
  }

  const handleSelectGl = (accountId: string | null) => {
    if (!review) return
    void updateReview('gl', () => selectGl(review.review_id, accountId), 'GL selection updated.')
  }

  const handleApprove = () => {
    if (!review) return
    void updateReview('approve', () => approveReview(review.review_id), 'Review approved.')
  }

  const handleReject = () => {
    if (!review) return
    void updateReview('reject', () => rejectReview(review.review_id), 'Review rejected.')
  }

  const handleRequestCorrection = () => {
    if (!review) return
    setDraft(null)
    setDraftError(null)
    setCopyMessage(null)
    setBusyAction('request_correction')
    setNotice(null)
    logFrontendEvent('info', 'review.action_started', { action: 'request_correction' })
    void requestCorrection(review.review_id)
      .then(async (updated) => {
        setReview(updated)
        setDraftOpen(true)
        setNotice({ message: 'Correction request recorded. Generate a draft only if you need one.', variant: 'default' })
        logFrontendEvent('info', 'review.action_completed', { action: 'request_correction', state: updated.state })
        await refreshHistory()
      })
      .catch((error: unknown) => {
        setNotice({ message: messageFor(error, 'Could not request a correction.'), variant: 'destructive' })
        logFrontendEvent('error', 'review.action_failed', { action: 'request_correction' })
      })
      .finally(() => setBusyAction(null))
  }

  const handleGenerateDraft = () => {
    if (!review) return
    setBusyAction('draft')
    setDraftError(null)
    setCopyMessage(null)
    logFrontendEvent('info', 'review.action_started', { action: 'generate_draft' })
    void generateCorrectionDraft(review.review_id)
      .then((result) => {
        setDraft(result.draft.text)
        logFrontendEvent('info', 'review.action_completed', { action: 'generate_draft' })
      })
      .catch((error: unknown) => {
        setDraftError(messageFor(error, 'The local VLM could not generate a correction draft.'))
        logFrontendEvent('error', 'review.action_failed', { action: 'generate_draft' })
      })
      .finally(() => setBusyAction(null))
  }

  const handleCopyDraft = () => {
    if (!draft) return
    void navigator.clipboard.writeText(draft)
      .then(() => {
        setCopyMessage('Draft copied to the clipboard.')
        logFrontendEvent('info', 'clipboard.copy_completed', { outcome: 'success' })
      })
      .catch(() => {
        setCopyMessage('Could not copy the draft. Select the text and copy it manually.')
        logFrontendEvent('warn', 'clipboard.copy_completed', { outcome: 'failure' })
      })
  }

  const handleDelete = async () => {
    if (!pendingDeleteId) return
    setBusyAction('delete')
    setNotice(null)
    logFrontendEvent('info', 'review.action_started', { action: 'delete' })
    try {
      await deleteReview(pendingDeleteId)
      if (review?.review_id === pendingDeleteId) resetToWelcome()
      setPendingDeleteId(null)
      setNotice({ message: 'Review and its original local file were deleted.', variant: 'default' })
      logFrontendEvent('info', 'review.action_completed', { action: 'delete' })
      await refreshHistory()
    } catch (error: unknown) {
      setNotice({ message: messageFor(error, 'Could not delete the review.'), variant: 'destructive' })
      logFrontendEvent('error', 'review.action_failed', { action: 'delete' })
    } finally {
      setBusyAction(null)
    }
  }

  const previewFileName = review?.original_file.filename ?? preview?.fileName ?? null
  const previewMediaType = review?.original_file.media_type ?? preview?.mediaType ?? null
  const previewSize = review?.original_file.size_bytes ?? selectedFile?.size ?? null

  return (
    <div className="min-h-svh bg-muted/30">
      <header className="border-b bg-background">
        <div className="mx-auto flex min-h-16 max-w-360 items-center justify-between gap-4 px-4 sm:px-6">
          <button type="button" className="text-left text-sm font-semibold tracking-tight" onClick={resetToWelcome}>Invoice Review</button>
          <div className="flex items-center gap-3">
            <Badge variant="outline" className={healthState === 'healthy' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : healthState === 'unavailable' ? 'border-red-200 bg-red-50 text-red-700' : 'border-amber-200 bg-amber-50 text-amber-700'}>
              {healthState === 'healthy' ? 'Local API ready' : healthState === 'unavailable' ? 'Local API unavailable' : 'Checking API'}
            </Badge>
            {review && <Button type="button" variant="outline" size="sm" onClick={resetToWelcome} disabled={busy}><Plus className="size-4" />New review</Button>}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-360 space-y-6 px-4 py-8 sm:px-6 lg:py-10">
        <section className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div className="max-w-2xl space-y-2">
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Review supplier documents before bookkeeping.</h1>
            <p className="text-sm leading-6 text-muted-foreground">Upload a local invoice or receipt, inspect evidence and policy results, then make the accounting decision.</p>
          </div>
          {healthState === 'unavailable' && <Button type="button" variant="outline" onClick={() => void checkHealth()}><RefreshCw className="size-4" />Retry API</Button>}
        </section>

        {healthState === 'unavailable' && (
          <Alert variant="destructive"><AlertTitle>Backend unavailable</AlertTitle><AlertDescription>{healthMessage}</AlertDescription></Alert>
        )}
        {notice && <Alert variant={notice.variant}><AlertTitle>{notice.variant === 'destructive' ? 'Action needs attention' : 'Review updated'}</AlertTitle><AlertDescription>{notice.message}</AlertDescription></Alert>}

        {!review ? (
          <section className="grid gap-6 lg:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)]">
            <UploadPanel file={selectedFile} validationMessage={fileError} busy={busy} onFileChange={handleFileChange} onRemove={handleRemoveFile} onUpload={() => void handleUpload()} />
            <DocumentPreview fileName={previewFileName} mediaType={previewMediaType} sizeBytes={previewSize} previewUrl={preview?.url ?? null} />
          </section>
        ) : (
          <section className="grid items-start gap-6 lg:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)]">
            <DocumentPreview fileName={previewFileName} mediaType={previewMediaType} sizeBytes={previewSize} previewUrl={preview?.url ?? null} />
            <ReviewPanel
              review={review}
              accounts={accounts}
              busy={busy}
              processBusy={busyAction === 'process'}
              processingStage={processingStage}
              onProcess={handleProcess}
              onSelectGl={handleSelectGl}
              onApprove={handleApprove}
              onReject={handleReject}
              onRequestCorrection={handleRequestCorrection}
              onDelete={() => setPendingDeleteId(review.review_id)}
            />
          </section>
        )}

        <HistoryPanel
          history={history}
          activeReviewId={review?.review_id ?? null}
          loading={historyLoading}
          busy={busy}
          onOpen={(reviewId) => void handleOpenReview(reviewId)}
          onDelete={setPendingDeleteId}
        />
      </main>

      <CorrectionDraftDialog
        open={draftOpen}
        draft={draft}
        error={draftError}
        copyMessage={copyMessage}
        generating={busyAction === 'draft'}
        onOpenChange={setDraftOpen}
        onGenerate={handleGenerateDraft}
        onCopy={handleCopyDraft}
      />

      <AlertDialog open={pendingDeleteId !== null} onOpenChange={(open) => { if (!open) setPendingDeleteId(null) }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this review?</AlertDialogTitle>
            <AlertDialogDescription>This permanently removes the review and its original local file. You can upload the document again afterwards.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" disabled={busy} onClick={() => void handleDelete()}>Delete review</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export default App
