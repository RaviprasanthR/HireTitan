import { ArrowLeft } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router'
import { Button } from '@/components/ui/button'

type Props =
  /** Always opens this page: for a page whose parent is fixed (a search's summary → Explore). */
  | { to: string; fallback?: never; label?: string }
  /** Goes back to the previous page, or opens `fallback` when the page was opened directly. */
  | { fallback: string; to?: never; label?: string }

export function BackButton({ to, fallback, label = 'Back' }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  // the first page of a visit has the key "default"; any page reached in the app has its own
  const cameFromApp = location.key !== 'default'
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="-ml-2 text-muted-small"
      onClick={() => {
        if (to !== undefined) void navigate(to)
        else if (cameFromApp) void navigate(-1)
        // replace, so Back on the fallback page does not come straight back here
        else void navigate(fallback, { replace: true })
      }}
    >
      <ArrowLeft aria-hidden />
      {label}
    </Button>
  )
}
