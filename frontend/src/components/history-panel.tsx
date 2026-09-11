import { FolderOpen, Trash2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatDate, formatDateTime, formatMoney } from '@/lib/format'
import type { ReviewState, ReviewSummary } from '@/lib/types'

type HistoryPanelProps = {
  history: ReviewSummary[]
  activeReviewId: string | null
  loading: boolean
  busy: boolean
  onOpen: (reviewId: string) => void
  onDelete: (reviewId: string) => void
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

function stateLabel(state: ReviewState): string {
  return state.replaceAll('_', ' ')
}

export function HistoryPanel({ history, activeReviewId, loading, busy, onOpen, onDelete }: HistoryPanelProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Review history</CardTitle>
        <CardDescription>Reopen a local review or explicitly delete it and its original file.</CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3"><Skeleton className="h-10" /><Skeleton className="h-10" /><Skeleton className="h-10" /></div>
        ) : history.length === 0 ? (
          <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">No local reviews yet.</div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Document</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden md:table-cell">Updated</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {history.map((item) => (
                <TableRow key={item.review_id} className={item.review_id === activeReviewId ? 'bg-muted/60' : undefined}>
                  <TableCell className="max-w-48">
                    <p className="truncate font-medium">{item.counterparty ?? 'Unprocessed document'}</p>
                    <p className="text-xs text-muted-foreground">{item.document_date ? formatDate(item.document_date) : 'Date pending'}{item.total ? ` · ${formatMoney(item.total, item.currency)}` : ''}</p>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={stateClasses[item.state]}>{stateLabel(item.state)}</Badge>
                    {item.blocking_issue_count > 0 && <p className="mt-1 text-xs text-destructive">{item.blocking_issue_count} blocking</p>}
                    {item.failure_message && <p className="mt-1 text-xs text-destructive">Needs retry</p>}
                  </TableCell>
                  <TableCell className="hidden whitespace-nowrap text-xs text-muted-foreground md:table-cell">{formatDateTime(item.updated_at)}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button type="button" variant="ghost" size="icon" disabled={busy} onClick={() => onOpen(item.review_id)} aria-label="Open review"><FolderOpen className="size-4" /></Button>
                      <Button type="button" variant="ghost" size="icon" disabled={busy} onClick={() => onDelete(item.review_id)} aria-label="Delete review"><Trash2 className="size-4 text-destructive" /></Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
