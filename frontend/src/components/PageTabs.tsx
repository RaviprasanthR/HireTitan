import { NavLink } from 'react-router'

export interface PageTab {
  to: string
  label: string
}

/** Tabs that are addresses: each tab is a link, the open one is underlined (Home, Settings). */
export function PageTabs({ label, tabs }: { label: string; tabs: readonly PageTab[] }) {
  return (
    <nav aria-label={label} className="flex flex-wrap gap-2 border-b border-divider">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end
          className={({ isActive }) =>
            `-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              isActive
                ? 'border-[#f0a35e] text-[#f0a35e]'
                : 'border-transparent text-muted-small hover:text-foreground'
            }`
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}
