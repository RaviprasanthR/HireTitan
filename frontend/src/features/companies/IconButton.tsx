import { Button } from '@/components/ui/button'

/** A ghost icon button with a tooltip and its own colours: the row actions and the contacts. */
export function IconButton({
  title,
  label,
  tone,
  children,
  ...props
}: {
  title: string
  label: string
  tone: string
  children: React.ReactNode
} & Omit<React.ComponentProps<typeof Button>, 'title' | 'aria-label' | 'children'>) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      title={title}
      aria-label={label}
      className={tone}
      {...props}
    >
      {children}
    </Button>
  )
}
