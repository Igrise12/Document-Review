export type DocumentType = 'invoice' | 'receipt'

export type ReviewState =
  | 'uploaded'
  | 'processing'
  | 'ready_for_review'
  | 'approved'
  | 'rejected'
  | 'correction_requested'
  | 'failed'

export type CurrencyCode = { code: string; display: string }
export type VatId = { normalized: string; display: string }

export type SourceDocument = {
  filename: string
  media_type: 'application/pdf' | 'image/png' | 'image/jpeg'
  size_bytes: number
  page_count: number
  uploaded_at: string
  processed_at: string | null
}

export type InvoiceFields = {
  vendor_name: string | null
  vendor_vat_id: VatId | null
  customer_name: string | null
  customer_vat_id: VatId | null
  invoice_number: string | null
  invoice_date: string | null
  due_date: string | null
  purchase_order: string | null
  currency: CurrencyCode | null
  subtotal: string | null
  total_tax: string | null
  invoice_total: string | null
}

export type ReceiptFields = {
  merchant: string | null
  transaction_date: string | null
  expense_category: string | null
  currency: CurrencyCode | null
  subtotal: string | null
  vat_total: string | null
  total: string | null
}

export type InvoiceDocument = {
  document_type: 'invoice'
  source: SourceDocument
  fields: InvoiceFields
}

export type ReceiptDocument = {
  document_type: 'receipt'
  source: SourceDocument
  fields: ReceiptFields
}

export type NormalizedDocument = InvoiceDocument | ReceiptDocument

export type FieldEvidence = {
  value: unknown
  confidence: string | null
  source: 'primary' | 'vlm' | 'manual' | null
  status: 'primary' | 'vlm_fallback' | 'merged' | 'missing' | 'conflict'
  page: number | null
  bounding_box: { x: number; y: number; width: number; height: number } | null
  text_context: string | null
  primary_value: unknown
  vlm_value: unknown
}

export type DocumentIssue = {
  code: string
  severity: 'error' | 'warning'
  message: string
  field: string | null
}

export type GLAccount = { account_id: string; label: string; category: string }

export type GLReview = {
  suggestion: { account_id: string; rationale: string; confidence: string } | null
  selection: { account_id: string | null } | null
  validation: { account_id: string | null; valid: boolean; reason: string | null } | null
}

export type ReviewSummary = {
  review_id: string
  state: ReviewState
  document_type: DocumentType | null
  counterparty: string | null
  document_date: string | null
  currency: string | null
  total: string | null
  blocking_issue_count: number
  updated_at: string
  failure_message: string | null
}

export type ReviewDetail = {
  review_id: string
  state: ReviewState
  document_type: DocumentType | null
  original_file: {
    filename: string
    media_type: 'application/pdf' | 'image/png' | 'image/jpeg'
    size_bytes: number
    page_count: number | null
    uploaded_at: string
  }
  created_at: string
  updated_at: string
  processed_at: string | null
  normalized_document: NormalizedDocument | null
  evidence: Record<string, FieldEvidence>
  conflicts: Record<string, FieldEvidence>
  issues: DocumentIssue[]
  blocking_issue_count: number
  gl_review: GLReview | null
  approval_allowed: boolean
  provider_runs: Record<string, unknown>
  action_metadata: Record<string, unknown> | null
  failure_message: string | null
}

export type CorrectionDraftResult = {
  draft: { text: string }
  provider_run: Record<string, unknown>
}
