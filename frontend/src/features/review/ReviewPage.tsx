import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'

type ReviewItem = components['schemas']['ReviewItemOut']

export function ReviewPage() {
  const query = useQuery({
    queryKey: ['review-items'],
    queryFn: () => apiFetch<ReviewItem[]>('/review-items'),
    refetchOnWindowFocus: false,
  })

  let body
  if (query.isPending) body = <p>Loading…</p>
  else if (query.isError || !Array.isArray(query.data)) {
    body = <p role="alert">Could not load the review list.</p>
  } else if (query.data.length === 0) body = <p>Nothing is waiting for you.</p>
  else {
    body = (
      <ul className="max-w-2xl space-y-3">
        {query.data.map((item) => (
          <li key={item.id} className="rounded-lg bg-surface p-4">
            <Link to={item.target} className="font-medium underline">
              {item.title}
            </Link>
            <p className="text-sm text-muted-small">
              {new Date(item.updated_at).toLocaleString()}
            </p>
          </li>
        ))}
      </ul>
    )
  }

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Review</h1>
      {body}
    </section>
  )
}
