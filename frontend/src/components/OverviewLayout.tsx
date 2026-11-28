/**
 * A list with its overview (counts and charts) beside it (FR-023a). The list comes first in the
 * reading order; from 1280px the overview is drawn in a left column, below that it follows the
 * list. The overview holds no controls, so the focus order never jumps. An overview that renders
 * nothing takes no room (theme.css `.ht-overview-layout`).
 */
export function OverviewLayout({
  label,
  overview,
  overviewFirst = false,
  children,
}: {
  label: string
  overview: React.ReactNode
  overviewFirst?: boolean // below 1280px draw the overview above the list (DOM order is kept)
  children: React.ReactNode
}) {
  return (
    <div className={`ht-overview-layout grid gap-4${overviewFirst ? ' ht-overview-first' : ''}`}>
      <div className="ht-overview-main min-w-0 space-y-4">{children}</div>
      {overview != null && (
        <aside aria-label={label} className="ht-overview min-w-0 space-y-4">
          {overview}
        </aside>
      )}
    </div>
  )
}
