import { Clipboard, Sparkles } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'

type CorrectionDraftDialogProps = {
  open: boolean
  draft: string | null
  error: string | null
  copyMessage: string | null
  generating: boolean
  onOpenChange: (open: boolean) => void
  onGenerate: () => void
  onCopy: () => void
}

export function CorrectionDraftDialog({
  open,
  draft,
  error,
  copyMessage,
  generating,
  onOpenChange,
  onGenerate,
  onCopy,
}: CorrectionDraftDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Correction request draft</DialogTitle>
          <DialogDescription>
            Generate a professional draft for the supplier. Invoice Review never sends it.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Alert variant="destructive">
            <AlertTitle>Draft unavailable</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {draft ? (
          <div className="space-y-2">
            <Textarea aria-label="Correction request draft" readOnly value={draft} className="min-h-64 resize-y" />
            {copyMessage && <p className="text-sm text-muted-foreground" aria-live="polite">{copyMessage}</p>}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">The draft is generated only after you request it.</p>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          {draft ? (
            <Button type="button" onClick={onCopy}><Clipboard className="size-4" />Copy draft</Button>
          ) : (
            <Button type="button" onClick={onGenerate} disabled={generating}>
              <Sparkles className="size-4" />{generating ? 'Generating draft…' : 'Generate draft'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
