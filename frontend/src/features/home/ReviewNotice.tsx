import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { apiFetch } from '@/api/client'

/** "N items need your review" above the Home tabs; nothing when nothing waits. */
export function ReviewNotice() {
  const query = useQuery({
    queryKey: ['review-items'],
    queryFn: () => apiFetch<unknown[]>('/review-items'),
    refetchOnWindowFocus: false,
  })
  const count = Array.isArray(query.data) ? query.data.length : 0
  if (count === 0) return null
  return (
    <p className="rounded-lg bg-surface px-4 py-2 text-sm">
      <Link to="/review" className="font-medium text-link underline">
        {count === 1 ? '1 item needs your review' : `${count} items need your review`}
      </Link>
    </p>
  )
}
