import { FileImage, FileText } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatBytes } from '@/lib/format'

type DocumentPreviewProps = {
  fileName: string | null
  mediaType: 'application/pdf' | 'image/png' | 'image/jpeg' | null
  sizeBytes?: number | null
  previewUrl: string | null
}

export function DocumentPreview({ fileName, mediaType, sizeBytes, previewUrl }: DocumentPreviewProps) {
  const isPdf = mediaType === 'application/pdf'

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row items-start justify-between gap-4 border-b pb-5">
        <div className="min-w-0 space-y-1">
          <CardTitle>Original document</CardTitle>
          <p className="truncate text-sm text-muted-foreground">{fileName ?? 'Choose a document to preview it here.'}</p>
        </div>
        {mediaType && <Badge variant="secondary">{isPdf ? 'PDF' : 'Image'}</Badge>}
      </CardHeader>
      <CardContent className="p-0">
        <div className="flex min-h-105 items-center justify-center bg-muted/40 p-4">
          {previewUrl && isPdf && (
            <iframe className="h-[36rem] w-full rounded-md border bg-white" title={`Preview of ${fileName ?? 'document'}`} src={previewUrl} />
          )}
          {previewUrl && !isPdf && (
            <img className="max-h-[36rem] w-full rounded-md object-contain" src={previewUrl} alt={`Preview of ${fileName ?? 'document'}`} />
          )}
          {!previewUrl && (
            <div className="flex max-w-xs flex-col items-center gap-3 text-center text-muted-foreground">
              {mediaType ? <FileImage className="size-10" /> : <FileText className="size-10" />}
              <p className="text-sm">The original file will stay beside the extracted review.</p>
            </div>
          )}
        </div>
        {sizeBytes !== null && sizeBytes !== undefined && (
          <p className="border-t px-6 py-3 text-xs text-muted-foreground">{formatBytes(sizeBytes)}</p>
        )}
      </CardContent>
    </Card>
  )
}
