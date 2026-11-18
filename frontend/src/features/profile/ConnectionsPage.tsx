import { Users } from 'lucide-react'
import { Section } from '@/features/jobs/Section'
import { LinkedinImport } from './LinkedinImport'

/** Profile tab: bring in your LinkedIn connections as contacts at the companies on your list. */
export function ConnectionsPage() {
  return (
    <section className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold">Connections</h1>
      <Section
        title="Import from LinkedIn"
        hint="Choose the Connections.csv from your LinkedIn data export. People who work at a company on your Companies list become its contacts; everyone else is left out. Importing the same file again adds nobody twice. The file is read on this computer and never sent to AI."
        icon={Users}
        tone="ht-section-people"
        as="h2"
      >
        <LinkedinImport />
      </Section>
    </section>
  )
}
