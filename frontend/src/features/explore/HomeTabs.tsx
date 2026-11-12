import { NavLink } from 'react-router'

const TABS = [
  { to: '/pipeline', label: 'In pipeline' },
  { to: '/', label: 'Explore' },
]

/** The two tabs of Home: new jobs to look at, and the jobs already applied to or asked about. */
export function HomeTabs() {
  return (
    <nav aria-label="Home tabs" className="flex gap-2 border-b border-divider">
      {TABS.map((tab) => (
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
