import { PageTabs } from '@/components/PageTabs'

const TABS = [
  { to: '/', label: 'In pipeline' },
  { to: '/explore', label: 'Explore' },
]

/** The two tabs of Jobs: the jobs already applied to or asked about (the default), and new jobs to look at. */
export function HomeTabs() {
  return <PageTabs label="Jobs tabs" tabs={TABS} />
}
