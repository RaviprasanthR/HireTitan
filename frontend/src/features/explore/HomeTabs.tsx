import { PageTabs } from '@/components/PageTabs'

const TABS = [
  { to: '/', label: 'In pipeline' },
  { to: '/explore', label: 'Explore' },
]

/** The two tabs of Home: the jobs already applied to or asked about (the default), and new jobs to look at. */
export function HomeTabs() {
  return <PageTabs label="Home tabs" tabs={TABS} />
}
