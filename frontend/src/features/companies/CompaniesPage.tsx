import {
  ArrowDown,
  ArrowUp,
  Building2,
  Globe,
  Pencil,
  Plus,
  Radar,
  Search,
  StickyNote,
  Users,
} from 'lucide-react'
import { useState } from 'react'
import { ApiError } from '@/api/client'
import { StageChip } from '@/components/StageChip'
import { Button } from '@/components/ui/button'
import { formatDay } from '@/features/explore/api'
import { AddCompanyDialog } from './AddCompanyDialog'
import { IconButton } from './IconButton'
import { BOARD_STATUS, useCompanies, useDeleteCompany, useEditCompany, type Company } from './api'
import { CompanyPanel } from './CompanyPanel'
import { Field, inputClass } from './Field'

type SortKey = 'name' | 'city' | 'pipeline' | 'contacts' | 'note'
type Sort = { key: SortKey; dir: 'asc' | 'desc' }

/** The quiet raised chip used by the toolbar buttons. */
const TOOL_CHIP =
  'border-transparent bg-raised text-foreground hover:bg-raised hover:text-link aria-selected:ring-1 aria-selected:ring-link/60'

const CHIP = 'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs whitespace-nowrap'

/** How far the person's jobs at this company have got: Applied, Inquired, or nothing. */
function PipelineChip({ company }: { company: Company }) {
  if (company.pipeline === 'applied' || company.pipeline === 'inquired')
    return <StageChip stage={company.pipeline} />
  return <span className="text-xs text-muted-small">Not set</span>
}

/** A small round icon button; each action has its own colour and a tooltip. */
function EditForm({
  company,
  onDone,
  onDelete,
}: {
  company: Company
  onDone: () => void
  onDelete: () => void
}) {
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
      <div className="flex flex-wrap gap-2 sm:col-span-2">
        <Button type="submit" size="sm" disabled={edit.isPending} variant="success">
          Save
        </Button>
        <Button type="button" variant="cancel" size="sm" onClick={onDone}>
          Cancel
        </Button>
        {company.hidden && (
          // hiding is gone from the list; a company hidden before can come back to searches
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={edit.isPending}
            onClick={() =>
              edit.mutate({ id: company.id, changes: { hidden: false } }, { onSuccess: onDone })
            }
          >
            Search this company again
          </Button>
        )}
        <Button
          type="button"
          variant="danger"
          size="sm"
          className="ml-auto"
          aria-label={`Delete ${company.name}`}
          onClick={onDelete}
        >
          Delete
        </Button>
      </div>
    </form>
  )
}

// The columns of the list: the header row and every company row share them, so they line up.
const COLUMNS =
  'md:grid md:grid-cols-[minmax(9rem,14rem)_minmax(6rem,9rem)_6.5rem_8.5rem_minmax(8rem,1fr)_12rem] md:items-center md:gap-x-4'

const shortUrl = (url: string) => url.replace(/^https?:\/\//, '').replace(/\/$/, '')

function ExternalLink({ url }: { url: string }) {
  return (
    <a href={url} target="_blank" rel="noreferrer noopener" className="text-link underline">
      {shortUrl(url)}
    </a>
  )
}

const PIPELINE_TEXT = {
  applied: 'You have applied to a job here',
  inquired: 'You have asked about a job here',
  none: 'Nothing in your pipeline here',
}

/** Everything the list knows about a company, shown when its row is expanded. */
function Details({ company, checked }: { company: Company; checked: string | null }) {
  const board = [
    company.board_status === 'unresolved' && !company.careers_url
      ? 'No careers page: searches skip it'
      : BOARD_STATUS[company.board_status],
    company.ats_vendor,
    company.board_id,
  ]
    .filter(Boolean)
    .join(' · ')
  const lastChecked = checked
    ? `Last checked ${checked}${company.last_check_result ? ` · ${company.last_check_result}` : ''}`
    : 'Not checked yet'
  const rows: [string, React.ReactNode][] = [
    ['Location', company.city ?? 'Not set'],
    ['Pipeline', PIPELINE_TEXT[company.pipeline ?? 'none']],
    ['Website', company.website ? <ExternalLink url={company.website} /> : 'Not set'],
    ['Careers page', company.careers_url ? <ExternalLink url={company.careers_url} /> : 'Not set'],
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
  if (company.hidden) rows.push(['Searches', 'Left out (hidden before)'])
  // the rows split into two cards, in the look of the Preferences and Search rules pages
  const whereLabels = ['Location', 'Pipeline', 'Website', 'Careers page']
  const where = rows.filter(([label]) => whereLabels.includes(label))
  const source = rows.filter(([label]) => !where.some(([w]) => w === label))
  return (
    <section aria-label={`Details for ${company.name}`} className="grid gap-3 md:grid-cols-2">
      <DetailCard
        title="Company"
        icon={<Building2 aria-hidden className="size-4" />}
        tone="ht-company-where"
        rows={where}
      />
      <DetailCard
        title="Job source"
        icon={<Radar aria-hidden className="size-4" />}
        tone="ht-company-source"
        rows={source}
      />
    </section>
  )
}

function DetailCard({
  title,
  icon,
  tone,
  rows,
}: {
  title: string
  icon: React.ReactNode
  tone: string
  rows: [string, React.ReactNode][]
}) {
  return (
    <div className={`ht-detail-card ${tone}`}>
      <h3 className="ht-detail-heading">
        {icon}
        {title}
      </h3>
      <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-small">{label}</dt>
            <dd className="min-w-0 break-words">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function CompanyRow({ company }: { company: Company }) {
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [showPanel, setShowPanel] = useState(false)
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
      className={`ht-list-card relative space-y-2 px-3 py-1.5 transition-colors duration-200 after:absolute after:inset-x-3 after:bottom-0 after:h-px after:bg-border motion-reduce:transition-none ${
        // the tint is for a resting row: an open, edited or about-to-go row stays as it is
        showPanel || editing || confirming ? '' : 'hover:bg-raised'
      }`}
    >
      {/* A click anywhere on the row opens or closes it; the name is the same switch for the
          keyboard. Links and buttons in the row keep their own job. */}
      <div
        className={`flex min-h-8 cursor-pointer flex-wrap items-center gap-x-4 gap-y-1 ${COLUMNS}`}
        onClick={(event) => {
          const target = event.target as HTMLElement
          if (target.closest('a, button, input, select, textarea, label')) return
          setShowPanel(!showPanel)
        }}
      >
        <div className="min-w-0">
          <h2 className="min-w-0 font-semibold md:truncate">
            <button
              type="button"
              aria-expanded={showPanel}
              aria-label={`Details for ${company.name}`}
              onClick={() => setShowPanel(!showPanel)}
              className="max-w-full rounded text-left hover:text-link md:truncate focus-visible:ring-2 focus-visible:ring-ring"
            >
              {company.name}
            </button>
            {company.hidden && <span className="ml-2 text-sm text-muted-small">(hidden)</span>}
          </h2>
        </div>
        <span className="min-w-0 truncate text-sm text-muted-small">{company.city ?? ''}</span>
        <PipelineChip company={company} />
        <span
          className={`${CHIP} w-fit ${
            company.contact_count > 0
              ? 'bg-raised text-subtle'
              : 'text-muted-small'
          }`}
        >
          <Users aria-hidden className="size-3" />
          {contacts}
        </span>
        <span
          className="flex min-w-0 flex-1 items-center gap-1.5 text-xs text-subtle md:min-w-0"
          title={company.note_preview ?? undefined}
        >
          {company.note_preview && (
            <>
              <StickyNote aria-hidden className="size-3 shrink-0" />
              <span className="truncate">{company.note_preview}</span>
            </>
          )}
        </span>
        <div className="ml-auto flex justify-end gap-1 md:ml-0">
          {!editing && !confirming && (
            <>
              {company.website ? (
                <Button
                  asChild
                  variant="ghost"
                  size="icon-sm"
                  className="text-subtle hover:bg-raised hover:text-foreground"
                >
                  <a
                    href={company.website}
                    target="_blank"
                    rel="noreferrer noopener"
                    title="Company site"
                    aria-label={`Open ${company.name} website`}
                  >
                    <Globe aria-hidden />
                  </a>
                </Button>
              ) : (
                <span className="size-7" aria-hidden />
              )}
              <IconButton
                title="Edit"
                label={`Edit ${company.name}`}
                tone="text-subtle hover:bg-raised hover:text-foreground"
                onClick={() => setEditing(true)}
              >
                <Pencil aria-hidden />
              </IconButton>
            </>
          )}
        </div>
      </div>
      {editing && (
        <EditForm
          company={company}
          onDone={() => setEditing(false)}
          onDelete={() => {
            setEditing(false)
            setConfirming(true)
          }}
        />
      )}
      {showPanel && (
        <div className="space-y-3 pt-2 pb-2">
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
              variant="danger"
            >
              Yes, delete
            </Button>
            <Button type="button" variant="cancel" size="sm" onClick={() => setConfirming(false)}>
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
  pipeline: 'pipeline',
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
    return c.pipeline === 'applied' ? 2 : c.pipeline === 'inquired' ? 1 : 0
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
    : key === 'pipeline'
      ? sort.dir === 'desc'
        ? 'applied, then inquired, first'
        : 'applied, then inquired, last'
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
        className={`-ml-1 inline-flex items-center gap-1 rounded px-1 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring ${
          active ? 'text-foreground' : ''
        } ${extra}`}
      >
        {text}
        {active &&
          (sort.dir === 'asc' ? (
            <ArrowUp aria-hidden className="size-3 text-warning" />
          ) : (
            <ArrowDown aria-hidden className="size-3 text-warning" />
          ))}
      </button>
    )
  }
  return (
    <div className={`ht-thead-row hidden px-3 py-3 [scrollbar-gutter:stable] ${COLUMNS}`}>
      {button('name', 'Company')}
      {button('city', 'Location')}
      {button('pipeline', 'Pipeline')}
      {button('contacts', 'Contacts')}
      {button('note', 'Note')}
      <span />
    </div>
  )
}

/** The company list: a sortable table with an expandable row for each company. */
export function CompaniesPage() {
  const [adding, setAdding] = useState(false)
  const companies = useCompanies('all')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<Sort>({ key: 'name', dir: 'asc' })
  const all = companies.data?.items ?? []
  const needle = query.trim().toLowerCase()
  const shown = all.filter(
    (c) => !needle || `${c.name} ${c.city ?? ''}`.toLowerCase().includes(needle),
  )
  const items = [...shown].sort(compareBy(sort))
  // A new column starts with its natural order: A to Z for text, most first for counts and the pipeline.
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
          ? 'No companies match this search.'
          : 'No companies yet. Add one with the button above.'}
      </p>
    )
  else
    body = (
      <ul aria-label="Companies">
        {items.map((company) => (
          <CompanyRow key={company.id} company={company} />
        ))}
      </ul>
    )

  return (
    <section className="flex min-h-0 flex-1 flex-col">
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
          {!adding && (
            <Button type="button" size="sm" className={TOOL_CHIP} onClick={() => setAdding(true)}>
              <Plus aria-hidden />
              Add a company
            </Button>
          )}
        </div>
        {loaded && <HeaderRow sort={sort} onSort={sortBy} />}
      </div>
      <div className="min-h-48 flex-1 overflow-y-auto [scrollbar-gutter:stable]">{body}</div>
      {adding && <AddCompanyDialog onClose={() => setAdding(false)} />}
    </section>
  )
}
