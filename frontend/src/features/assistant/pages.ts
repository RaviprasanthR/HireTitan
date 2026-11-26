/** Plain names for the pages Mikasa links to. */
const PAGE_NAMES: Record<string, string> = {
  '/': 'Jobs',
  '/explore': 'Explore',
  '/companies': 'Companies',
  '/profile': 'Profile',
  '/profile/preferences': 'Preferences',
  '/profile/search-rules': 'Search rules',
  '/profile/versions': 'Profile versions',
  '/settings': 'Settings',
  '/settings/gmail': 'Settings → Gmail',
  '/search/history': 'Search history',
  '/review': 'Review',
}

export function pageName(path: string): string {
  const known = PAGE_NAMES[path]
  if (known) return known
  if (path.startsWith('/jobs/')) return path.endsWith('/resume') ? 'the tailored resume' : 'the job'
  if (path.startsWith('/search/runs/')) return 'the search'
  return path
}
