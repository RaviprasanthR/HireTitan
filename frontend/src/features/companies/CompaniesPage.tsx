import {
  ArrowDown,
  ArrowUp,
  Briefcase,
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  Globe,
  Pencil,
  Search,
  StickyNote,
  Trash2,
  Users,
} from 'lucide-react'
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
type SortKey = 'name' | 'city' | 'openings' | 'contacts' | 'note'
type Sort = { key: SortKey; dir: 'asc' | 'desc' }

const countOf = (company: Company, area: Area): number | null =>
  company.openings ? (company.openings[area] ?? 0) : null

// One colour per area, so a glance tells them apart.
const AREA_STYLE: Record<Area, string> = {
  frontend: 'bg-violet-500/15 text-violet-300 hover:bg-violet-500/25',
  backend: 'bg-sky-500/15 text-sky-300 hover:bg-sky-500/25',
  qa: 'bg-amber-500/15 text-amber-300 hover:bg-amber-500/25',
}
const CHIP = 'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs whitespace-nowrap'

const totalOf = (company: Company): number | null =>
  company.openings ? AREAS.reduce((sum, { area }) => sum + (countOf(company, area) ?? 0), 0) : null

/** The row shows one number: all the open roles. It opens the company's jobs in Explore; a company
 * never searched has no number, and zero has nothing to open. */
function OpenTotal({ company }: { company: Company }) {
  const total = totalOf(company)
  if (total === null) return <span className="text-xs text-muted-small">Not searched yet</span>
  const text = `${total} open roles`
  return total > 0 ? (
    <Link
      to={`/?company_id=${company.id}`}
      className={`${CHIP} w-fit bg-sky-500/15 text-sky-300 transition-colors hover:bg-sky-500/30`}
    >
      <Briefcase aria-hidden className="size-3" />
      {text}
    </Link>
  ) : (
    <span className={`${CHIP} w-fit bg-white/5 text-muted-small opacity-70`}>
      <Briefcase aria-hidden className="size-3" />
      {text}
    </span>
  )
}

/** The open roles by area, shown in the expanded details: each count opens the jobs behind it. */
function Breakdown({ company }: { company: Company }) {
  if (!company.openings) return <>Not searched yet</>
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

// The columns of the list: the header row and every company row share them, so they line up.
const COLUMNS =
  'md:grid md:grid-cols-[minmax(9rem,14rem)_minmax(6rem,9rem)_9rem_8.5rem_minmax(8rem,1fr)_10rem] md:items-center md:gap-x-4'

const shortUrl = (url: string) => url.replace(/^https?:\/\//, '').replace(/\/$/, '')

function ExternalLink({ url }: { url: string }) {
  return (
    <a href={url} target="_blank" rel="noreferrer noopener" className="text-link underline">
      {shortUrl(url)}
    </a>
  )
}

/** Everything the list knows about a company, shown when its row is expanded. */
function Details({ company, checked }: { company: Company; checked: string | null }) {
  const board = [BOARD_STATUS[company.board_status], company.ats_vendor, company.board_id]
    .filter(Boolean)
    .join(' · ')
  const lastChecked = checked
    ? `Last checked ${checked}${company.last_check_result ? ` · ${company.last_check_result}` : ''}`
    : 'Not checked yet'
  const rows: [string, React.ReactNode][] = [
    ['Location', company.city ?? '—'],
    ['Open roles', <Breakdown key="roles" company={company} />],
    ['Website', company.website ? <ExternalLink url={company.website} /> : '—'],
    ['Careers page', company.careers_url ? <ExternalLink url={company.careers_url} /> : '—'],
    ['Job board', board],
    [
      'Source',
      company.origin === 'built_in'
        ? `Built-in list${company.user_modified ? ' (edited by you)' : ''}`
        : 'Added by you',
    ],
    ['Last check', lastChecked],
  ]
  if (company.last_check_error) rows.push(['Last problem', company.last_check_error])
  rows.push(['Visibility', company.hidden ? 'Hidden from the list' : 'Shown'])
  return (
    <section aria-label={`Details for ${company.name}`}>
      <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-small">{label}</dt>
            <dd className="min-w-0 break-words">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
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
    <li
      aria-label={company.name}
      className="space-y-2 rounded-lg bg-surface px-3 py-1 ring-1 ring-transparent transition duration-200 ease-out hover:-translate-y-px hover:bg-white/[0.04] hover:shadow-[0_8px_24px_-12px_rgba(76,201,240,0.45)] hover:ring-cyan-400/30 motion-reduce:transition-none motion-reduce:hover:translate-y-0"
    >
      <div className={`flex min-h-8 flex-wrap items-center gap-x-4 gap-y-1 ${COLUMNS}`}>
        <h2 className="min-w-0 truncate font-semibold">
          {company.name}
          {company.hidden && <span className="ml-2 text-sm text-muted-small">(hidden)</span>}
        </h2>
        <span className="min-w-0 truncate text-sm text-muted-small">{company.city ?? ''}</span>
        <OpenTotal company={company} />
        <span
          className={`${CHIP} w-fit ${
            company.contact_count > 0
              ? 'bg-teal-500/15 text-teal-300'
              : 'bg-white/5 text-muted-small opacity-70'
          }`}
        >
          <Users aria-hidden className="size-3" />
          {contacts}
        </span>
        <span
          className="flex min-w-0 flex-1 items-center gap-1.5 text-xs text-rose-200/80 md:min-w-0"
          title={company.note_preview ?? undefined}
        >
          {company.note_preview && (
            <>
              <StickyNote aria-hidden className="size-3 shrink-0 text-rose-300" />
              <span className="truncate">{company.note_preview}</span>
            </>
          )}
        </span>
        <div className="ml-auto flex justify-end gap-1 md:ml-0">
          {!editing && !confirming && (
            <>
              <IconButton
                title="Details"
                label={`Details for ${company.name}`}
                tone="text-cyan-300 hover:bg-cyan-500/20 hover:text-cyan-200"
                aria-expanded={showPanel}
                onClick={() => setShowPanel(!showPanel)}
              >
                {showPanel ? <ChevronUp aria-hidden /> : <ChevronDown aria-hidden />}
              </IconButton>
              {company.careers_url ? (
                <Button
                  asChild
                  variant="ghost"
                  size="icon-sm"
                  className="text-indigo-300 hover:bg-indigo-500/20 hover:text-indigo-200"
                >
                  <a
                    href={company.careers_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    title="Careers page"
                    aria-label={`Open ${company.name} careers page`}
                  >
                    <Globe aria-hidden />
                  </a>
                </Button>
              ) : (
                <span className="size-7" aria-hidden />
              )}
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
            </>
          )}
        </div>
      </div>
      {manual && (
        <p className="pb-1 text-sm">
          {checked ? `Last checked ${checked}` : 'Not checked yet'}
          {company.last_check_error && (
            <span className="ml-3 text-muted-small">{company.last_check_error}</span>
          )}
        </p>
      )}
      {edit.isError && !editing && (
        <p role="alert" className="text-sm text-danger">
          {edit.error.message}
        </p>
      )}
      {editing && <EditForm company={company} onDone={() => setEditing(false)} />}
      {showPanel && (
        <div className="space-y-4 border-t border-white/10 pt-3 pb-2">
          <Details company={company} checked={checked} />
          <CompanyPanel companyId={company.id} companyName={company.name} />
        </div>
      )}
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

const TEXT_SORTS: SortKey[] = ['name', 'city', 'note']
const SORT_NAMES: Record<SortKey, string> = {
  name: 'company',
  city: 'location',
  openings: 'open roles',
  contacts: 'contacts',
  note: 'note',
}

/** Compare two companies on one column. A missing value (no city, no note, never searched) is
 * always last, whichever way the column is sorted; ties keep the company name order. */
function compareBy(sort: Sort) {
  const value = (c: Company): string | number | null => {
    if (sort.key === 'name') return c.name.toLowerCase()
    if (sort.key === 'city') return c.city ? c.city.toLowerCase() : null
    if (sort.key === 'note') return c.note_preview ? c.note_preview.toLowerCase() : null
    if (sort.key === 'contacts') return c.contact_count
    return totalOf(c)
  }
  const sign = sort.dir === 'asc' ? 1 : -1
  return (a: Company, b: Company) => {
    const x = value(a)
    const y = value(b)
    if (x === null && y !== null) return 1
    if (y === null && x !== null) return -1
    if (x !== null && y !== null && x !== y) return (x < y ? -1 : 1) * sign
    return a.name.localeCompare(b.name)
  }
}

function sortLabel(key: SortKey, sort: Sort): string {
  const base = `Sort by ${SORT_NAMES[key]}`
  if (sort.key !== key) return base
  const text = TEXT_SORTS.includes(key)
    ? sort.dir === 'asc'
      ? 'A to Z'
      : 'Z to A'
    : sort.dir === 'asc'
      ? 'fewest first'
      : 'most first'
  return `${base}, now ${text}`
}

/** The column titles. Each one sorts the list; a second click reverses it. */
function HeaderRow({ sort, onSort }: { sort: Sort; onSort: (key: SortKey) => void }) {
  const button = (key: SortKey, text: string, extra = '') => {
    const active = sort.key === key
    return (
      <button
        type="button"
        aria-label={sortLabel(key, sort)}
        title={SORT_NAMES[key]}
        onClick={() => onSort(key)}
        className={`-ml-1 inline-flex items-center gap-1 rounded px-1 uppercase hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring ${
          active ? 'text-foreground' : ''
        } ${extra}`}
      >
        {text}
        {active &&
          (sort.dir === 'asc' ? (
            <ArrowUp aria-hidden className="size-3" />
          ) : (
            <ArrowDown aria-hidden className="size-3" />
          ))}
      </button>
    )
  }
  return (
    <div
      className={`hidden overflow-hidden rounded-lg border border-cyan-300/15 bg-cyan-400/10 px-3 py-2 text-xs font-semibold tracking-wider text-cyan-100/80 shadow-sm [scrollbar-gutter:stable] ${COLUMNS}`}
    >
      {button('name', 'Company')}
      {button('city', 'Location')}
      {button('openings', 'Open roles')}
      {button('contacts', 'Contacts')}
      {button('note', 'Note')}
      <span />
    </div>
  )
}

/** The company list: a sortable table with an expandable row for each company. */
export function CompaniesPage() {
  const [filter, setFilter] = useState<CompanyFilter>('all')
  const [adding, setAdding] = useState(false)
  const [tools, setTools] = useState(false)
  const companies = useCompanies(filter)
  const [show, setShow] = useState<Show>('all')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<Sort>({ key: 'name', dir: 'asc' })
  const all = companies.data?.items ?? []
  const needle = query.trim().toLowerCase()
  const shown = all
    .filter((c) =>
      show === 'all'
        ? true
        : show === 'contacts'
          ? c.contact_count > 0
          : (countOf(c, show) ?? 0) > 0,
    )
    .filter((c) => !needle || `${c.name} ${c.city ?? ''}`.toLowerCase().includes(needle))
  const items = [...shown].sort(compareBy(sort))
  // A new column starts with its natural order: A to Z for text, most first for counts.
  const sortBy = (key: SortKey) =>
    setSort((now) =>
      now.key === key
        ? { key, dir: now.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: TEXT_SORTS.includes(key) ? 'asc' : 'desc' },
    )

  const loaded = !companies.isPending && !companies.isError && items.length > 0
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
      <ul aria-label="Companies" className="space-y-1.5">
        {items.map((company) => (
          <CompanyRow key={company.id} company={company} manual={filter === 'check_manually'} />
        ))}
      </ul>
    )

  return (
    <section className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="shrink-0 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold">Companies</h1>
          <label className="relative min-w-48 flex-1 sm:max-w-sm">
            <Search
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-small"
            />
            <input
              type="search"
              aria-label="Search companies"
              placeholder="Search companies…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className={`${inputClass} w-full pl-8`}
            />
          </label>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-expanded={tools}
              onClick={() => setTools(!tools)}
            >
              Import / export
            </Button>
            {!adding && (
              <Button type="button" size="sm" onClick={() => setAdding(true)}>
                Add a company
              </Button>
            )}
          </div>
        </div>
        {adding && <AddCompanyDialog onClose={() => setAdding(false)} />}
        <div hidden={!tools} className="rounded-lg bg-surface p-3">
          <ImportExport />
        </div>
        <div className="flex flex-wrap items-center gap-3">
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
          <form aria-label="Company filters" onSubmit={(e) => e.preventDefault()}>
            <label className="flex items-center gap-2 text-sm">
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
          </form>
        </div>
        {loaded && <HeaderRow sort={sort} onSort={sortBy} />}
      </div>
      <div className="min-h-48 flex-1 overflow-y-auto [scrollbar-gutter:stable]">{body}</div>
    </section>
  )
}
