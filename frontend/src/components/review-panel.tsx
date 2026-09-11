import { AlertCircle, CheckCircle2, CircleAlert, RotateCw, Send, Trash2, XCircle } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { fieldLabel, formatDate, formatDateTime, formatEvidenceValue, formatMoney } from '@/lib/format'
import type { GLAccount, NormalizedDocument, ReviewDetail, ReviewState } from '@/lib/types'

type ReviewPanelProps = {
  review: ReviewDetail
  accounts: GLAccount[]
  busy: boolean
  onProcess: () => void
  onSelectGl: (accountId: string | null) => void
  onApprove: () => void
  onReject: () => void
  onRequestCorrection: () => void
  onDelete: () => void
}

const stateLabels: Record<ReviewState, string> = {
  uploaded: 'Uploaded',
  processing: 'Processing',
  ready_for_review: 'Ready for review',
  approved: 'Approved',
  rejected: 'Rejected',
  correction_requested: 'Correction requested',
  failed: 'Processing failed',
}

const stateClasses: Record<ReviewState, string> = {
  uploaded: 'border-blue-200 bg-blue-50 text-blue-700',
  processing: 'border-amber-200 bg-amber-50 text-amber-700',
  ready_for_review: 'border-violet-200 bg-violet-50 text-violet-700',
  approved: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  rejected: 'border-slate-200 bg-slate-100 text-slate-700',
  correction_requested: 'border-orange-200 bg-orange-50 text-orange-700',
  failed: 'border-red-200 bg-red-50 text-red-700',
}

function IssueList({ review }: { review: ReviewDetail }) {
  const errors = review.issues.filter((issue) => issue.severity === 'error')
  const warnings = review.issues.filter((issue) => issue.severity === 'warning')

  return (
    <Card>
      <CardHeader>
        <CardTitle>Policy checks</CardTitle>
        <CardDescription>Errors block approval. Warnings remain visible for review.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <IssueGroup title="Blocking errors" issues={errors} icon={<XCircle className="size-4 text-destructive" />} empty="No blocking errors." />
        <Separator />
        <IssueGroup title="Warnings" issues={warnings} icon={<CircleAlert className="size-4 text-amber-600" />} empty="No warnings." />
      </CardContent>
    </Card>
  )
}

function IssueGroup({
  title,
  issues,
  icon,
  empty,
}: {
  title: string
  issues: ReviewDetail['issues']
  icon: React.ReactNode
  empty: string
}) {
  return (
    <section aria-label={title}>
      <h3 className="mb-3 text-sm font-medium">{title}</h3>
      {issues.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ul className="space-y-3">
          {issues.map((issue) => (
            <li key={`${issue.code}-${issue.field ?? 'review'}`} className="flex gap-3 text-sm">
              <span className="mt-0.5 shrink-0">{icon}</span>
              <span>
                <span className="block font-medium">{issue.field ? fieldLabel(issue.field) : issue.code}</span>
                <span className="text-muted-foreground">{issue.message}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function FieldGrid({ document }: { document: NormalizedDocument }) {
  const currency = document.fields.currency
  const rows: Array<{ label: string; value: unknown }> = document.document_type === 'invoice'
    ? [
        { label: 'Supplier', value: document.fields.vendor_name },
        { label: 'Supplier VAT ID', value: document.fields.vendor_vat_id },
        { label: 'Customer', value: document.fields.customer_name },
        { label: 'Customer VAT ID', value: document.fields.customer_vat_id },
        { label: 'Invoice number', value: document.fields.invoice_number },
        { label: 'Invoice date', value: formatDate(document.fields.invoice_date) },
        { label: 'Due date', value: formatDate(document.fields.due_date) },
        { label: 'Purchase order', value: document.fields.purchase_order },
        { label: 'Currency', value: document.fields.currency?.display ?? null },
        { label: 'Subtotal', value: formatMoney(document.fields.subtotal, currency) },
        { label: 'VAT total', value: formatMoney(document.fields.total_tax, currency) },
        { label: 'Invoice total', value: formatMoney(document.fields.invoice_total, currency) },
      ]
    : [
        { label: 'Merchant', value: document.fields.merchant },
        { label: 'Transaction date', value: formatDate(document.fields.transaction_date) },
        { label: 'Expense category', value: document.fields.expense_category },
        { label: 'Currency', value: document.fields.currency?.display ?? null },
        { label: 'Subtotal', value: formatMoney(document.fields.subtotal, currency) },
        { label: 'VAT total', value: formatMoney(document.fields.vat_total, currency) },
        { label: 'Receipt total', value: formatMoney(document.fields.total, currency) },
      ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>{document.document_type === 'invoice' ? 'Invoice details' : 'Receipt details'}</CardTitle>
        <CardDescription>Normalized values before policy and human review.</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
          {rows.map((row) => (
            <div key={row.label} className="min-w-0">
              <dt className="text-xs font-medium text-muted-foreground">{row.label}</dt>
              <dd className="mt-1 break-words text-sm font-medium">{formatEvidenceValue(row.value)}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}

function EvidenceList({ review }: { review: ReviewDetail }) {
  const entries = Object.entries(review.evidence)
  if (entries.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Evidence and provenance</CardTitle>
        <CardDescription>Primary parser values stay authoritative; VLM values only fill missing fields.</CardDescription>
      </CardHeader>
      <CardContent>
        <TooltipProvider>
          <div className="space-y-3">
            {entries.map(([field, evidence]) => (
              <details key={field} className="rounded-md border p-3">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm">
                  <span className="font-medium">{fieldLabel(field)}</span>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span><EvidenceBadge status={evidence.status} /></span>
                    </TooltipTrigger>
                    <TooltipContent>{evidenceHelp(evidence.status)}</TooltipContent>
                  </Tooltip>
                </summary>
                <div className="mt-3 space-y-3 border-t pt-3 text-sm">
                  <EvidenceRow label="Resolved value" value={formatEvidenceValue(evidence.value)} />
                  {evidence.confidence && <EvidenceRow label="Confidence" value={`${Math.round(Number(evidence.confidence) * 100)}%`} />}
                  {evidence.page && <EvidenceRow label="Source page" value={String(evidence.page)} />}
                  {evidence.status === 'conflict' && (
                    <div className="grid gap-2 rounded-md bg-amber-50 p-3 text-amber-950 sm:grid-cols-2">
                      <EvidenceRow label="Primary candidate" value={formatEvidenceValue(evidence.primary_value)} />
                      <EvidenceRow label="VLM candidate" value={formatEvidenceValue(evidence.vlm_value)} />
                    </div>
                  )}
                  {evidence.text_context && <EvidenceRow label="Evidence context" value={evidence.text_context} />}
                </div>
              </details>
            ))}
          </div>
        </TooltipProvider>
      </CardContent>
    </Card>
  )
}

function EvidenceRow({ label, value }: { label: string; value: string }) {
  return <p><span className="text-muted-foreground">{label}: </span>{value}</p>
}

function EvidenceBadge({ status }: { status: ReviewDetail['evidence'][string]['status'] }) {
  const label = status === 'vlm_fallback' ? 'VLM fallback' : status.replaceAll('_', ' ')
  const classes = status === 'conflict'
    ? 'border-amber-200 bg-amber-50 text-amber-700'
    : status === 'missing'
      ? 'border-slate-200 bg-slate-100 text-slate-600'
      : status === 'vlm_fallback'
        ? 'border-blue-200 bg-blue-50 text-blue-700'
        : 'border-emerald-200 bg-emerald-50 text-emerald-700'
  return <Badge variant="outline" className={classes}>{label}</Badge>
}

function evidenceHelp(status: ReviewDetail['evidence'][string]['status']): string {
  if (status === 'conflict') return 'Primary and VLM values disagree. Both candidates are preserved.'
  if (status === 'vlm_fallback') return 'The primary parser had no value, so the independent VLM filled this field.'
  if (status === 'missing') return 'Neither extraction source produced a usable value.'
  if (status === 'merged') return 'Both sources agreed on this value.'
  return 'The primary parser provided this value.'
}

function GLDecisionPanel({
  review,
  accounts,
  busy,
  onSelectGl,
  onApprove,
  onReject,
  onRequestCorrection,
}: Omit<ReviewPanelProps, 'onDelete' | 'onProcess'>) {
  const ready = review.state === 'ready_for_review'
  const suggestion = review.gl_review?.suggestion
  const selectedId = review.gl_review?.selection?.account_id ?? 'unselected'
  const validationMessage = review.gl_review?.validation?.reason

  return (
    <Card>
      <CardHeader>
        <CardTitle>Decision</CardTitle>
        <CardDescription>Northstar policy controls approval. Maya chooses the final GL account.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="gl-selection">Northstar GL account</Label>
          <Select
            value={selectedId}
            disabled={!ready || busy}
            onValueChange={(value) => onSelectGl(value === 'unselected' ? null : value)}
          >
            <SelectTrigger id="gl-selection"><SelectValue placeholder="Select an account" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="unselected">No account selected</SelectItem>
              {accounts.map((account) => (
                <SelectItem key={account.account_id} value={account.account_id}>
                  {account.account_id} — {account.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {validationMessage && <p className="text-sm text-muted-foreground">{validationMessage}</p>}
        </div>

        {suggestion && (
          <Alert>
            <CheckCircle2 className="mb-2 size-4" />
            <AlertTitle>VLM suggestion: {suggestion.account_id}</AlertTitle>
            <AlertDescription>
              {suggestion.rationale} Confidence: {Math.round(Number(suggestion.confidence) * 100)}%.
            </AlertDescription>
          </Alert>
        )}

        {ready && !review.approval_allowed && (
          <Alert>
            <AlertCircle className="mb-2 size-4" />
            <AlertTitle>Approval is blocked</AlertTitle>
            <AlertDescription>Resolve blocking policy errors and select a valid GL account before approval.</AlertDescription>
          </Alert>
        )}

        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={!ready || !review.approval_allowed || busy} onClick={onApprove}>Approve review</Button>
          <Button type="button" variant="outline" disabled={!ready || busy} onClick={onReject}>Reject review</Button>
          <Button
            type="button"
            variant="outline"
            disabled={!ready || review.blocking_issue_count === 0 || busy}
            onClick={onRequestCorrection}
          >
            <Send className="size-4" />Request correction
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export function ReviewPanel({
  review,
  accounts,
  busy,
  onProcess,
  onSelectGl,
  onApprove,
  onReject,
  onRequestCorrection,
  onDelete,
}: ReviewPanelProps) {
  const document = review.normalized_document
  const needsProcessing = review.state === 'uploaded' || review.state === 'failed'
  const processing = review.state === 'processing'

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
          <div>
            <div className="flex items-center gap-2"><Badge variant="outline" className={stateClasses[review.state]}>{stateLabels[review.state]}</Badge>{review.document_type && <span className="text-sm capitalize text-muted-foreground">{review.document_type}</span>}</div>
            <p className="mt-2 text-sm text-muted-foreground">Updated {formatDateTime(review.updated_at)}</p>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={onDelete} disabled={busy}><Trash2 className="size-4" />Delete review</Button>
        </CardContent>
      </Card>

      {needsProcessing && (
        <Alert variant={review.state === 'failed' ? 'destructive' : 'default'}>
          <AlertTitle>{review.state === 'failed' ? 'Processing did not finish' : 'Document uploaded'}</AlertTitle>
          <AlertDescription className="mt-2 flex flex-wrap items-center gap-3">
            <span>{review.failure_message ?? 'Start the local parser, independent review, merge, policy checks, and GL suggestion.'}</span>
            <Button type="button" size="sm" variant={review.state === 'failed' ? 'outline' : 'default'} disabled={busy} onClick={onProcess}>
              <RotateCw className="size-4" />{review.state === 'failed' ? 'Retry processing' : 'Process document'}
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {processing && (
        <Alert>
          <AlertTitle>Processing document</AlertTitle>
          <AlertDescription>The local parser, independent review, deterministic merge, policy checks, and GL suggestion are running in this request.</AlertDescription>
        </Alert>
      )}

      {document && <FieldGrid document={document} />}
      {document && <IssueList review={review} />}
      {document && <EvidenceList review={review} />}
      {document && <GLDecisionPanel review={review} accounts={accounts} busy={busy} onSelectGl={onSelectGl} onApprove={onApprove} onReject={onReject} onRequestCorrection={onRequestCorrection} />}
    </div>
  )
}
