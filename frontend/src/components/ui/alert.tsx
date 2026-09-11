import { cva, type VariantProps } from 'class-variance-authority'
import type { ComponentProps } from 'react'

import { cn } from '@/lib/utils'

const alertVariants = cva('relative w-full rounded-lg border px-4 py-3 text-sm', {
  variants: {
    variant: {
      default: 'bg-background text-foreground',
      destructive: 'border-destructive/40 text-destructive',
    },
  },
  defaultVariants: { variant: 'default' },
})

function Alert({ className, variant, ...props }: ComponentProps<'div'> & VariantProps<typeof alertVariants>) {
  return <div role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
}

function AlertTitle({ className, ...props }: ComponentProps<'h5'>) {
  return <h5 className={cn('mb-1 font-medium leading-none tracking-tight', className)} {...props} />
}

function AlertDescription({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('text-sm [&_p]:leading-relaxed', className)} {...props} />
}

export { Alert, AlertDescription, AlertTitle }
