import { NavLink } from 'react-router'

const TABS = [
  { to: '/', label: 'In pipeline' },
  { to: '/explore', label: 'Explore' },
]

/** The two tabs of Home: the jobs already applied to or asked about (the default), and new jobs to look at. */
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
