import { useId } from 'react'
import { cn } from '@/lib/utils'

/** The HireTitan logo: a map pin with a necktie cut out of it, filled with a gold to orange to
 *  rust gradient and a soft warm glow. The cut-outs show the page behind. Traced from Ravi's logo
 *  image (2026-11-15); the same shape and colours are in `public/favicon.svg` and
 *  `docs/assets/logo.svg`. */
export function Logo({ className }: { className?: string }) {
  // Each logo on a page needs its own gradient id; React's ids contain colons, which url() dislikes.
  const gradient = `ht-logo-${useId().replace(/:/g, '')}`
  return (
    <svg
      data-logo
      aria-hidden="true"
      viewBox="0 0 76 106"
      fillRule="evenodd"
      className={cn('ht-logo h-7 w-auto shrink-0', className)}
    >
      <defs>
        <linearGradient id={gradient} x1="0.15" y1="0" x2="0.85" y2="1">
          <stop offset="0" stopColor="#ffe0a3" />
          <stop offset="0.45" stopColor="#f0a35e" />
          <stop offset="1" stopColor="#d9532f" />
        </linearGradient>
      </defs>
      <path
        fill={`url(#${gradient})`}
        d="M38 104 7.4 58.7a37 37 0 1 1 61.2 0Z M19 39a19 19 0 1 0 38 0 19 19 0 1 0-38 0Z M32 60.5h12l-3.8 8L44.5 88.5 38 97.5 31.5 88.5 35.8 68.5Z"
      />
    </svg>
  )
}
