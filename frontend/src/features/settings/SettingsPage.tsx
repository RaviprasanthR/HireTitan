import { Navigate, useParams, useSearchParams } from 'react-router'
import { PageTabs } from '@/components/PageTabs'
import { AiSection } from './AiSection'
import { DeleteAllData } from './DeleteAllData'
import { GmailSection } from './GmailSection'

const TABS = [
  { to: '/settings/ai', label: 'AI' },
  { to: '/settings/gmail', label: 'Gmail job alerts' },
  { to: '/settings/data', label: 'Your data' },
] as const
const TAB_IDS = ['ai', 'gmail', 'data']

function DataSection() {
  return (
    <section id="data-settings" aria-labelledby="data-heading" className="space-y-3">
      <header className="space-y-1">
        <h2 id="data-heading" className="text-lg font-semibold">
          Your data
        </h2>
        <p className="text-sm text-muted-small">
          Remove everything HireTitan holds about you and start again.
        </p>
      </header>
      <DeleteAllData />
    </section>
  )
}

/** Settings as tabs, like Home (002c US6, FR-028): AI, Gmail job alerts and Your data, each its
 *  own address. Plain /settings opens AI, or Gmail when Google has just sent the person back. */
export function SettingsPage() {
  const { tab } = useParams()
  const [search] = useSearchParams()
  if (!tab || !TAB_IDS.includes(tab)) {
    const to = search.has('gmail') ? 'gmail' : 'ai'
    const query = search.toString()
    return <Navigate replace to={`/settings/${to}${query ? `?${query}` : ''}`} />
  }
  return (
    <section className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-small">
          Everything here stays on this computer. Nothing is sent anywhere except to the AI
          provider and to Gmail, read-only.
        </p>
      </header>
      <PageTabs label="Settings tabs" tabs={TABS} />
      <div className="max-w-3xl">
        {tab === 'ai' && <AiSection />}
        {tab === 'gmail' && <GmailSection />}
        {tab === 'data' && <DataSection />}
      </div>
    </section>
  )
}
