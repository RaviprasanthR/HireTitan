import { useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { formatDay } from '@/features/explore/api'
import { AddCompanyDialog } from './AddCompanyDialog'
import {
  BOARD_STATUS,
  useCompanies,
  useDeleteCompany,
  useEditCompany,
  type Company,
  type CompanyFilter,
} from './api'
import { CompanyPanel } from './CompanyPanel'
import { Field, inputClass } from './Field'
import { ImportExport } from './ImportExport'

const TABS: { filter: CompanyFilter; label: string }[] = [
  { filter: 'all', label: 'All companies' },
  { filter: 'check_manually', label: 'Check manually' },
]

function EditForm({ company, onDone }: { company: Company; onDone: () => void }) {
  const edit = useEditCompany()
  const [values, setValues] = useState({
    name: company.name,
    city: company.city ?? '',
    website: company.website ?? '',
    careers_url: company.careers_url ?? '',
  })
  const error = edit.error instanceof ApiError ? edit.error : null
  const text = (key: keyof typeof values, label: string) => (
    <Field label={label} error={error?.fieldError(key)}>
      {(props) => (
        <input
          {...props}
          className={inputClass}
          value={values[key]}
          onChange={(event) => setValues({ ...values, [key]: event.target.value })}
        />
      )}
    </Field>
  )
  return (
    <form
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault()
        edit.mutate({ id: company.id, changes: values }, { onSuccess: onDone })
      }}
    >
      {text('name', 'Name')}
      {text('city', 'City')}
      {text('website', 'Website')}
      {text('careers_url', 'Careers page link')}
      {edit.isError && error?.fieldErrors.length === 0 && (
        <p role="alert" className="text-sm text-danger sm:col-span-2">
          {edit.error.message}
        </p>
      )}
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" size="sm" disabled={edit.isPending}>
          Save
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function CompanyRow({ company, manual }: { company: Company; manual: boolean }) {
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [showPanel, setShowPanel] = useState(false)
  const edit = useEditCompany()
  const remove = useDeleteCompany()
  const contacts = `${company.contact_count} contact${company.contact_count === 1 ? '' : 's'}`
  // Deleting one of the person's own companies removes its contacts and note (FR-023); a
  // shipped company is only hidden from the list, so its contacts stay.
  const goesWith =
    company.origin === 'user' && company.contact_count > 0
      ? ` Its ${contacts}${company.has_note ? ' and the note' : ''} will be deleted too.`
      : ''
  const checked = company.last_checked_at ? formatDay(company.last_checked_at.slice(0, 10)) : null

  return (
    <li className="space-y-2 rounded-lg bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="font-semibold">
            {company.name}
            {company.hidden && <span className="ml-2 text-sm text-muted-small">(hidden)</span>}
          </p>
          <p className="text-sm text-muted-small">
            {[company.city, BOARD_STATUS[company.board_status]].filter(Boolean).join(' · ')}
          </p>
          <p className="text-sm text-muted-small">
            {contacts}
            {company.has_note && ' · Has a note'}
          </p>
          {manual && (
            <div className="space-y-1 text-sm">
              {company.careers_url && (
                <a
                  href={company.careers_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-link underline"
                >
                  Open {company.name}’s careers page
                </a>
              )}
              <p>{checked ? `Last checked ${checked}` : 'Not checked yet'}</p>
              {company.last_check_error && (
                <p className="text-muted-small">{company.last_check_error}</p>
              )}
            </div>
          )}
        </div>
        {!editing && !confirming && (
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-expanded={showPanel}
              aria-label={`Contacts and note for ${company.name}`}
              onClick={() => setShowPanel(!showPanel)}
            >
              Contacts
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={edit.isPending}
              aria-label={`${company.hidden ? 'Show' : 'Hide'} ${company.name}`}
              onClick={() =>
                edit.mutate({
                  id: company.id,
                  changes: { hidden: !company.hidden },
                })
              }
            >
              {company.hidden ? 'Show' : 'Hide'}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label={`Edit ${company.name}`}
              onClick={() => setEditing(true)}
            >
              Edit
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label={`Delete ${company.name}`}
              onClick={() => setConfirming(true)}
            >
              Delete
            </Button>
          </div>
        )}
      </div>
      {edit.isError && !editing && (
        <p role="alert" className="text-sm text-danger">
          {edit.error.message}
        </p>
      )}
      {editing && <EditForm company={company} onDone={() => setEditing(false)} />}
      {showPanel && <CompanyPanel companyId={company.id} companyName={company.name} />}
      {confirming && (
        <div className="space-y-2">
          <p className="text-sm">
            Delete {company.name}?{' '}
            {company.origin === 'built_in'
              ? 'It will not come back with the shipped list.'
              : 'This cannot be undone.'}
            {goesWith}
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              disabled={remove.isPending}
              onClick={() => remove.mutate(company.id)}
            >
              Yes, delete
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setConfirming(false)}>
              Keep it
            </Button>
          </div>
          {remove.isError && (
            <p role="alert" className="text-sm text-danger">
              {remove.error.message}
            </p>
          )}
        </div>
      )}
    </li>
  )
}

/** The company list: board status, hide, edit, delete, add, the check-manually tab, CSV. */
export function CompaniesPage() {
  const [filter, setFilter] = useState<CompanyFilter>('all')
  const [adding, setAdding] = useState(false)
  const companies = useCompanies(filter)
  const items = companies.data?.items ?? []

  let body
  if (companies.isPending) body = <p>Loading…</p>
  else if (companies.isError) body = <p role="alert">Could not load the company list.</p>
  else if (items.length === 0)
    body = (
      <p>
        {filter === 'check_manually'
          ? 'Nothing to check by hand right now.'
          : 'No companies yet. Add one by its careers page link.'}
      </p>
    )
  else
    body = (
      <ul aria-label="Companies" className="space-y-3">
        {items.map((company) => (
          <CompanyRow key={company.id} company={company} manual={filter === 'check_manually'} />
        ))}
      </ul>
    )

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Companies</h1>
        {!adding && (
          <Button type="button" size="sm" onClick={() => setAdding(true)}>
            Add a company
          </Button>
        )}
      </div>
      {adding && <AddCompanyDialog onClose={() => setAdding(false)} />}
      <ImportExport />
      <div role="tablist" aria-label="Company lists" className="flex gap-2">
        {TABS.map((tab) => (
          <Button
            key={tab.filter}
            type="button"
            role="tab"
            aria-selected={filter === tab.filter}
            variant={filter === tab.filter ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilter(tab.filter)}
          >
            {tab.label}
          </Button>
        ))}
      </div>
      {body}
    </section>
  )
}
