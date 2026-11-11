import { Eye, EyeOff, Pencil, StickyNote, Trash2, Users } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
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

type Area = 'frontend' | 'backend' | 'qa'
const AREAS: { area: Area; label: string }[] = [
  { area: 'frontend', label: 'Front end' },
  { area: 'backend', label: 'Back end' },
  { area: 'qa', label: 'QA' },
]
type Show = 'all' | 'contacts' | Area
type SortBy = 'name' | Area

const countOf = (company: Company, area: Area): number | null =>
  company.openings ? (company.openings[area] ?? 0) : null

// One colour per area, so a glance tells them apart.
const AREA_STYLE: Record<Area, string> = {
  frontend: 'bg-violet-500/15 text-violet-300 hover:bg-violet-500/25',
  backend: 'bg-sky-500/15 text-sky-300 hover:bg-sky-500/25',
  qa: 'bg-amber-500/15 text-amber-300 hover:bg-amber-500/25',
}
const CHIP = 'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs whitespace-nowrap'

/** The open roles by area: each count opens the jobs behind it; a company never searched has none. */
function Openings({ company }: { company: Company }) {
  if (!company.openings)
    return <span className="text-xs text-muted-small">Open roles: Not searched yet</span>
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {AREAS.map(({ area, label }) => {
        const count = countOf(company, area) ?? 0
        const text = `${label}: ${count}`
        return count > 0 ? (
          <Link
            key={area}
            to={`/?company_id=${company.id}&area=${area}`}
            className={`${CHIP} ${AREA_STYLE[area]}`}
          >
            {text}
          </Link>
        ) : (
          <span key={area} className={`${CHIP} bg-white/5 text-muted-small opacity-70`}>
            {text}
          </span>
        )
      })}
    </span>
  )
}

/** A small round icon button; each action has its own colour and a tooltip. */
function IconButton({
  title,
  label,
  tone,
  children,
  ...props
}: {
  title: string
  label: string
  tone: string
  children: React.ReactNode
} & Omit<React.ComponentProps<typeof Button>, 'title' | 'aria-label' | 'children'>) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      title={title}
      aria-label={label}
      className={tone}
      {...props}
    >
      {children}
    </Button>
  )
}

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
    <li aria-label={company.name} className="space-y-2 rounded-lg bg-surface px-3 py-1.5">
      <div className="flex min-h-8 flex-wrap items-center gap-x-4 gap-y-1">
        <div className="flex min-w-0 items-baseline gap-2 md:w-72 md:shrink-0">
          <h2 className="truncate font-semibold">
            {company.name}
            {company.hidden && <span className="ml-2 text-sm text-muted-small">(hidden)</span>}
          </h2>
          <span className="truncate text-xs text-muted-small">
            {[company.city, BOARD_STATUS[company.board_status]].filter(Boolean).join(' · ')}
          </span>
        </div>
        <Openings company={company} />
        <span
          className={`${CHIP} ${
            company.contact_count > 0
              ? 'bg-teal-500/15 text-teal-300'
              : 'bg-white/5 text-muted-small opacity-70'
          }`}
        >
          <Users aria-hidden className="size-3" />
          {contacts}
        </span>
        <span
          className="flex min-w-0 flex-1 items-center gap-1.5 text-xs text-rose-200/80 md:min-w-40"
          title={company.note_preview ?? undefined}
        >
          {company.note_preview && (
            <>
              <StickyNote aria-hidden className="size-3 shrink-0 text-rose-300" />
              <span className="truncate">{company.note_preview}</span>
            </>
          )}
        </span>
        {!editing && !confirming && (
          <div className="ml-auto flex gap-1">
            <IconButton
              title="Contacts and note"
              label={`Contacts and note for ${company.name}`}
              tone="text-cyan-300 hover:bg-cyan-500/20 hover:text-cyan-200"
              aria-expanded={showPanel}
              onClick={() => setShowPanel(!showPanel)}
            >
              <Users aria-hidden />
            </IconButton>
            <IconButton
              title={company.hidden ? 'Show' : 'Hide'}
              label={`${company.hidden ? 'Show' : 'Hide'} ${company.name}`}
              tone="text-amber-300 hover:bg-amber-500/20 hover:text-amber-200"
              disabled={edit.isPending}
              onClick={() =>
                edit.mutate({
                  id: company.id,
                  changes: { hidden: !company.hidden },
                })
              }
            >
              {company.hidden ? <Eye aria-hidden /> : <EyeOff aria-hidden />}
            </IconButton>
            <IconButton
              title="Edit"
              label={`Edit ${company.name}`}
              tone="text-emerald-300 hover:bg-emerald-500/20 hover:text-emerald-200"
              onClick={() => setEditing(true)}
            >
              <Pencil aria-hidden />
            </IconButton>
            <IconButton
              title="Delete"
              label={`Delete ${company.name}`}
              tone="text-rose-300 hover:bg-rose-500/20 hover:text-rose-200"
              onClick={() => setConfirming(true)}
            >
              <Trash2 aria-hidden />
            </IconButton>
          </div>
        )}
      </div>
      {manual && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pb-1 text-sm">
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
          <span>{checked ? `Last checked ${checked}` : 'Not checked yet'}</span>
          {company.last_check_error && (
            <span className="text-muted-small">{company.last_check_error}</span>
          )}
        </div>
      )}
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
  const [show, setShow] = useState<Show>('all')
  const [sortBy, setSortBy] = useState<SortBy>('name')
  const all = companies.data?.items ?? []
  const shown = all.filter((c) =>
    show === 'all' ? true : show === 'contacts' ? c.contact_count > 0 : (countOf(c, show) ?? 0) > 0,
  )
  // Most openings first; a company never searched goes last. Equal counts keep the name order.
  const items =
    sortBy === 'name'
      ? shown
      : [...shown].sort((a, b) => (countOf(b, sortBy) ?? -1) - (countOf(a, sortBy) ?? -1))

  let body
  if (companies.isPending) body = <p>Loading…</p>
  else if (companies.isError) body = <p role="alert">Could not load the company list.</p>
  else if (items.length === 0)
    body = (
      <p>
        {all.length > 0
          ? 'No companies match this filter.'
          : filter === 'check_manually'
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
      <form
        aria-label="Company filters"
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => e.preventDefault()}
      >
        <label className="flex flex-col gap-1 text-sm">
          Show
          <select
            className={inputClass}
            value={show}
            onChange={(e) => setShow(e.target.value as Show)}
          >
            <option value="all">All companies</option>
            <option value="contacts">Has contacts</option>
            <option value="frontend">Has front end openings</option>
            <option value="backend">Has back end openings</option>
            <option value="qa">Has QA openings</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Sort by
          <select
            className={inputClass}
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortBy)}
          >
            <option value="name">Name</option>
            <option value="frontend">Front end openings</option>
            <option value="backend">Back end openings</option>
            <option value="qa">QA openings</option>
          </select>
        </label>
      </form>
      {body}
    </section>
  )
}
