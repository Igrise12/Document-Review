import type { ChangeEvent } from 'react'
import { FileUp, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { formatBytes } from '@/lib/format'

type UploadPanelProps = {
  file: File | null
  validationMessage: string | null
  busy: boolean
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void
  onRemove: () => void
  onUpload: () => void
}

export function UploadPanel({
  file,
  validationMessage,
  busy,
  onFileChange,
  onRemove,
  onUpload,
}: UploadPanelProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Start a review</CardTitle>
        <CardDescription>Upload one PDF, PNG, or JPEG. The file must be 4 MB or smaller.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="rounded-lg border border-dashed p-5">
          <Label className="flex cursor-pointer items-center gap-3" htmlFor="document-input">
            <span className="rounded-md border p-2 text-muted-foreground"><FileUp className="size-5" /></span>
            <span className="space-y-1">
              <span className="block text-sm font-medium">Choose a document</span>
              <span className="block text-xs font-normal text-muted-foreground">PDF, PNG, or JPEG only</span>
            </span>
          </Label>
          <Input
            id="document-input"
            className="sr-only"
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
            disabled={busy}
            onChange={onFileChange}
          />
        </div>

        {validationMessage && <p className="text-sm text-destructive" aria-live="polite">{validationMessage}</p>}

        {file && (
          <div className="flex items-center justify-between gap-4 rounded-lg bg-muted p-4">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{file.name}</p>
              <p className="text-xs text-muted-foreground">{formatBytes(file.size)}</p>
            </div>
            <Button type="button" variant="ghost" size="icon" onClick={onRemove} disabled={busy} aria-label="Remove selected document">
              <Trash2 className="size-4" />
            </Button>
          </div>
        )}

        <Button className="w-full" type="button" disabled={!file || busy} onClick={onUpload}>
          {busy ? 'Uploading document…' : 'Upload and review'}
        </Button>
      </CardContent>
    </Card>
  )
}
