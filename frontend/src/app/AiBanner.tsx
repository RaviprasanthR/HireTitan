import { Link } from 'react-router'
import { useStatus } from '@/api/useStatus'

/** Shown on every page while the AI cannot be used, with the steps to fix it (FR-030). */
export function AiBanner() {
  const status = useStatus().data?.ai?.status

  if (status === 'missing') {
    return (
      <div role="alert" aria-label="AI status" className="border-b border-danger bg-danger/10 px-8 py-3 text-sm">
        <strong>The AI key is missing.</strong> AI tasks are waiting. Add OPENAI_API_KEY to .env,
        then restart HireTitan. <Link to="/settings" className="text-link underline">See Settings</Link>
      </div>
    )
  }
  if (status === 'rejected') {
    return (
      <div role="alert" aria-label="AI status" className="border-b border-danger bg-danger/10 px-8 py-3 text-sm">
        <strong>The provider rejected your AI key.</strong> AI tasks are paused, not lost. Replace
        OPENAI_API_KEY in .env, then restart HireTitan.{' '}
        <Link to="/settings" className="text-link underline">See Settings</Link>
      </div>
    )
  }
  if (status === 'unreachable') {
    return (
      <div role="status" aria-label="AI status" className="border-b border-warning bg-warning/10 px-8 py-3 text-sm">
        The AI provider could not be reached. Check your internet connection; AI tasks will retry.
      </div>
    )
  }
  return null
}
