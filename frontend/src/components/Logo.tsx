import { cn } from '@/lib/utils'

/** The HireTitan logo: a map pin with a necktie cut out of it, in the flat lavender accent
 *  (DESIGN.md, Logo). The cut-outs show the page behind. Traced from Ravi's logo image
 *  (2026-11-15); the same shape and colour are in `public/favicon.svg` and `docs/assets/logo.svg`. */
const SHAPE =
  'M38 104 7.4 58.7a37 37 0 1 1 61.2 0Z M19 39a19 19 0 1 0 38 0 19 19 0 1 0-38 0Z M32 60.5h12l-3.8 8L44.5 88.5 38 97.5 31.5 88.5 35.8 68.5Z'

/** Flat copies of the shape stacked behind the front face (back to front), so a turn shows a solid
 *  edge, not a sheet of paper. 0.025em apart, between the front face (0.1em ahead of the middle) and the back face. */
const EDGE_DEPTHS = [-0.075, -0.05, -0.025, 0, 0.025, 0.05, 0.075]

export function Logo({ className }: { className?: string }) {
  return (
    <span className="ht-logo-3d">
      {EDGE_DEPTHS.map((z) => (
        <svg
          key={z}
          aria-hidden="true"
          viewBox="0 0 76 106"
          fillRule="evenodd"
          className={cn('ht-logo-edge', className)}
          style={{ transform: `translateZ(${z}em)` }}
        >
          <path d={SHAPE} />
        </svg>
      ))}
      {/* the back face: the same colour, turned round so both sides read alike */}
      <svg
        aria-hidden="true"
        viewBox="0 0 76 106"
        fillRule="evenodd"
        className={cn('ht-logo ht-logo-back h-7 w-auto shrink-0', className)}
        style={{ transform: 'translateZ(-0.1em) rotateY(180deg)' }}
      >
        <path fill="var(--ht-accent)" d={SHAPE} />
      </svg>
      <svg
        data-logo
        aria-hidden="true"
        viewBox="0 0 76 106"
        fillRule="evenodd"
        className={cn('ht-logo h-7 w-auto shrink-0', className)}
        style={{ transform: 'translateZ(0.1em)' }}
      >
        <path fill="var(--ht-accent)" d={SHAPE} />
      </svg>
    </span>
  )
}
