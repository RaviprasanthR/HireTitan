import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { useEvents } from '@/api/useEvents'
import { routes } from './routes'

function EventStream() {
  useEvents()
  return null
}

export function App() {
  const [queryClient] = useState(() => new QueryClient())
  const [router] = useState(() => createBrowserRouter(routes))
  return (
    <QueryClientProvider client={queryClient}>
      <EventStream />
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}
