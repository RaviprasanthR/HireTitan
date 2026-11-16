import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Ban, Briefcase, Pencil, RotateCcw, Sparkles } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link } from 'react-router'
import { ApiError, apiFetch } from '@/api/client'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'
import { LeaveGuard } from '@/features/jobs/interview/LeaveGuard'
import { ChipInput } from '@/features/preferences/ChipInput'
import { PlacesInput } from '@/features/preferences/PlacesInput'

type RuleSet = components['schemas']['RuleSetOut']
type Rules = components['schemas']['SearchRulesModel-Output']
type RuleItem = components['schemas']['RuleItemModel']
type PlaceRule = components['schemas']['PlaceRuleModel']
type RulesState = components['schemas']['RulesStateOut']

const QUERY_KEY = ['search-rules'] as const
const input = 'rounded-md border border-muted-foreground bg-background px-3 py-1.5 text-sm'

/** The areas of work, as a person would say them. */
const AREAS: { value: string; label: string }[] = [
  { value: 'back_end', label: 'Back end' },
  { value: 'front_end', label: 'Front end' },
  { value: 'full_stack', label: 'Full stack' },
  { value: 'mobile', label: 'Mobile' },
  { value: 'data', label: 'Data' },
  { value: 'qa', label: 'QA and testing' },
  { value: 'devops', label: 'DevOps' },
  { value: 'other', label: 'Other' },
]
const AREA_LABEL = Object.fromEntries(AREAS.map((a) => [a.value, a.label]))
const AREAS_MAX = 4

type GroupName = 'keep' | 'leave' | 'rank'

/** Where an error about a field is shown: next to the group the field belongs to. */
const GROUP_OF: Record<string, GroupName> = {
  title_words: 'keep',
  title_avoid: 'leave',
  blocked_locations: 'leave',
  max_age_days: 'leave',
  areas: 'rank',
  stack_keywords: 'rank',
  preferred_locations: 'rank',
}

const PLAIN_ERROR: Record<string, string> = {
  title_words: 'Add at least one job title.',
  max_age_days: 'Use a number of days from 1 to 365.',
  areas: `Pick up to ${AREAS_MAX} areas from the list.`,
}

const KEEP_INTRO = 'A job is kept when its title matches one of these roles.'
const LEAVE_INTRO =
  'A job is left out when its title has one of these words, it is in one of these places, or it is older than the limit. A job whose title names a language or framework you do not list is left out too.'
const RANK_INTRO = 'When the AI check is on, it uses these to judge whether a job suits you.'

function placeText(place: PlaceRule): string {
  return [place.city, place.country].filter(Boolean).join(', ')
}

function Group({
  title,
  intro,
  tone,
  Icon,
  errors,
  children,
}: {
  title: string
  intro: string
  tone: string
  Icon: typeof Briefcase
  errors?: string[]
  children: ReactNode
}) {
  return (
    <section aria-label={title} className={`ht-detail-card ht-${tone} space-y-3`}>
      <h2 className="ht-detail-heading">
        <Icon aria-hidden className="size-4" />
        {title}
      </h2>
      <p className="text-sm text-muted-small">{intro}</p>
      {children}
      {errors?.map((message) => (
        <p key={message} role="alert" className="text-sm text-danger">
          {message}
        </p>
      ))}
    </section>
  )
}

function Chips({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <p className="text-sm text-muted-small">{empty}</p>
  return (
    <ul className="flex flex-wrap gap-2">
      {items.map((text) => (
        <li key={text} className="rounded-full border border-border bg-muted px-3 py-1 text-sm">
          {text}
        </li>
      ))}
    </ul>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="text-sm font-medium">{label}</p>
      {children}
    </div>
  )
}

/** What Preferences decides: shown here, changed there. */
function FromPreferences({ rules }: { rules: Rules }) {
  const parts = [
    rules.work_modes.length ? `Work mode: ${rules.work_modes.join(', ')}` : null,
    rules.seniority.length ? `Seniority: ${rules.seniority.join(', ')}` : null,
    rules.years_experience ? `Years of experience: ${rules.years_experience}` : null,
  ].filter(Boolean)
  return (
    <p className="text-sm text-muted-small">
      {parts.length > 0 && <>{parts.join(' · ')}. </>}
      <Link to="/profile/preferences" className="text-link underline">
        Change these in Preferences
      </Link>
    </p>
  )
}

function ReadView({ rules }: { rules: Rules }) {
  return (
    <div className="grid items-stretch gap-5 lg:grid-cols-3">
      <Group title="Jobs we keep" intro={KEEP_INTRO} tone="rules-titles" Icon={Briefcase}>
        <Chips items={rules.title_words.map((i) => i.text)} empty="No job titles yet." />
      </Group>
      <Group title="Jobs we leave out" intro={LEAVE_INTRO} tone="rules-avoid" Icon={Ban}>
        <Field label="Words to avoid in titles">
          <Chips items={rules.title_avoid.map((i) => i.text)} empty="None." />
        </Field>
        <Field label="Places to skip">
          <Chips items={rules.blocked_locations.map(placeText)} empty="None." />
        </Field>
        <Field label="Oldest job we show">
          <p className="text-sm">{rules.max_age_days} days</p>
          <p className="text-xs text-muted-small">
            A job with no date is never left out for its age.
          </p>
        </Field>
      </Group>
      <Group title="What helps rank a job" intro={RANK_INTRO} tone="rules-skills" Icon={Sparkles}>
        <Field label="Your area of work">
          <Chips items={rules.areas.map((a) => AREA_LABEL[a] ?? a)} empty="Not set." />
        </Field>
        <Field label="Your skills">
          <Chips items={rules.stack_keywords.map((i) => i.text)} empty="None." />
        </Field>
        <Field label="Places you prefer">
          <Chips items={rules.preferred_locations.map(placeText)} empty="None." />
        </Field>
        <FromPreferences rules={rules} />
      </Group>
    </div>
  )
}

/** Edit a list of rule items as chips, keeping the origin of the ones that stay. */
function ItemsInput({
  id,
  items,
  onChange,
  placeholder,
}: {
  id: string
  items: RuleItem[]
  onChange: (next: RuleItem[]) => void
  placeholder: string
}) {
  return (
    <ChipInput
      id={id}
      value={items.map((i) => i.text)}
      placeholder={placeholder}
      onChange={(texts) =>
        onChange(
          texts.map((text) => items.find((i) => i.text === text) ?? { text, origin: 'user' }),
        )
      }
    />
  )
}

function PlaceRulesInput({
  label,
  places,
  onChange,
}: {
  label: string
  places: PlaceRule[]
  onChange: (next: PlaceRule[]) => void
}) {
  return (
    <PlacesInput
      label={label}
      defaultCountry="IN"
      value={places.map((p) => ({ city: p.city ?? '', country: p.country ?? '' }))}
      onChange={(next) =>
        onChange(
          next.map(
            (p) =>
              places.find((o) => (o.city ?? '') === p.city && (o.country ?? '') === p.country) ?? {
                city: p.city || null,
                country: p.country || null,
                origin: 'user',
              },
          ),
        )
      }
    />
  )
}

function errorsFor(error: ApiError | null, group: GroupName): string[] {
  if (!error) return []
  return error.fieldErrors
    .filter((e) => GROUP_OF[e.field] === group)
    .map((e) => PLAIN_ERROR[e.field] ?? e.message)
}

function RulesEditor({
  initial,
  fromProposal,
  onSaved,
  onCancel,
}: {
  initial: Rules
  fromProposal: boolean
  onSaved: () => void
  onCancel: () => void
}) {
  const [draft, setDraft] = useState<Rules>(initial)
  const set = <K extends keyof Rules>(key: K, value: Rules[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial)

  const save = useMutation({
    mutationFn: () => apiFetch<RuleSet>('/search/rules/approved', { method: 'PUT', json: draft }),
    onSuccess: onSaved,
  })
  const startOver = useMutation({
    mutationFn: () => apiFetch<Rules>('/search/rules/suggested'),
    onSuccess: (suggested) => setDraft(suggested),
  })
  const error = save.error instanceof ApiError ? save.error : null
  const otherError = error && error.fieldErrors.length === 0 ? error.detail : null

  return (
    <div className="space-y-4">
      <LeaveGuard when={dirty || save.isPending} />
      {fromProposal && (
        <p className="text-sm text-muted-small">
          You had changes in progress. They are shown here; nothing changes until you save.
        </p>
      )}
      <div className="grid items-stretch gap-5 lg:grid-cols-3">
        <Group
          title="Jobs we keep"
          intro={KEEP_INTRO}
          tone="rules-titles"
          Icon={Briefcase}
          errors={errorsFor(error, 'keep')}
        >
          <label className="text-sm font-medium" htmlFor="rule-titles">
            Job titles
          </label>
          <ItemsInput
            id="rule-titles"
            items={draft.title_words}
            onChange={(v) => set('title_words', v)}
            placeholder="Add a job title and press Enter"
          />
        </Group>
        <Group
          title="Jobs we leave out"
          intro={LEAVE_INTRO}
          tone="rules-avoid"
          Icon={Ban}
          errors={errorsFor(error, 'leave')}
        >
          <label className="text-sm font-medium" htmlFor="rule-avoid">
            Words to avoid in titles
          </label>
          <ItemsInput
            id="rule-avoid"
            items={draft.title_avoid}
            onChange={(v) => set('title_avoid', v)}
            placeholder="Add a word and press Enter"
          />
          <p className="text-sm font-medium">Places to skip</p>
          <PlaceRulesInput
            label="Places to skip"
            places={draft.blocked_locations}
            onChange={(v) => set('blocked_locations', v)}
          />
          <label className="flex items-center gap-2 text-sm">
            Oldest job we show (days)
            <input
              type="number"
              min={1}
              max={365}
              className={`${input} w-24`}
              value={draft.max_age_days}
              onChange={(e) => set('max_age_days', Number(e.target.value))}
            />
          </label>
        </Group>
        <Group
          title="What helps rank a job"
          intro={RANK_INTRO}
          tone="rules-skills"
          Icon={Sparkles}
          errors={errorsFor(error, 'rank')}
        >
          <fieldset className="space-y-1">
            <legend className="text-sm font-medium">Your area of work</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {AREAS.map((area) => {
                const checked = draft.areas.includes(area.value)
                return (
                  <label key={area.value} className="flex items-center gap-1.5 text-sm">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={!checked && draft.areas.length >= AREAS_MAX}
                      onChange={() =>
                        set(
                          'areas',
                          checked
                            ? draft.areas.filter((a) => a !== area.value)
                            : [...draft.areas, area.value],
                        )
                      }
                    />
                    {area.label}
                  </label>
                )
              })}
            </div>
          </fieldset>
          <label className="text-sm font-medium" htmlFor="rule-skills">
            Your skills
          </label>
          <ItemsInput
            id="rule-skills"
            items={draft.stack_keywords}
            onChange={(v) => set('stack_keywords', v)}
            placeholder="Add a skill and press Enter"
          />
          <p className="text-sm font-medium">Places you prefer</p>
          <PlaceRulesInput
            label="Places you prefer"
            places={draft.preferred_locations}
            onChange={(v) => set('preferred_locations', v)}
          />
          <FromPreferences rules={draft} />
        </Group>
      </div>
      {otherError && (
        <p role="alert" className="text-sm text-danger">
          {otherError}
        </p>
      )}
      {startOver.isError && (
        <p role="alert" className="text-sm text-danger">
          {startOver.error instanceof ApiError
            ? startOver.error.detail
            : 'Could not get suggested rules.'}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button variant="success" disabled={save.isPending} onClick={() => save.mutate()}>
          Save rules
        </Button>
        <Button variant="cancel" disabled={save.isPending} onClick={onCancel}>
          Cancel
        </Button>
        <Button
          variant="outline"
          disabled={save.isPending || startOver.isPending}
          title="Fill the editor with the rules suggested for your profile and preferences"
          onClick={() => startOver.mutate()}
        >
          <RotateCcw aria-hidden className="size-4" />
          Start over with suggested rules
        </Button>
      </div>
    </div>
  )
}

export function SearchRulesPage() {
  const client = useQueryClient()
  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => apiFetch<RulesState>('/search/rules'),
  })
  // the rules being edited, once the person chose to (a leftover open draft opens by itself)
  const [editing, setEditing] = useState<{ rules: Rules; key: string } | null>(null)
  const [saved, setSaved] = useState(false)

  const suggest = useMutation({
    mutationFn: () => apiFetch<Rules>('/search/rules/suggested'),
    onSuccess: (rules) => {
      setSaved(false)
      setEditing({ rules, key: `suggested-${Date.now()}` })
    },
  })
  const discard = useMutation({
    mutationFn: () => apiFetch('/search/rules/proposal', { method: 'DELETE' }),
    onSuccess: () => client.invalidateQueries({ queryKey: QUERY_KEY }),
  })

  if (query.isPending) return <p className="text-sm text-muted-small">Loading your search rules…</p>
  if (query.isError) {
    return (
      <p role="alert" className="text-sm text-danger">
        Could not load your search rules.
      </p>
    )
  }

  const { approved, proposal, stale } = query.data
  const leftover = !editing && proposal ? proposal : null
  const draft = editing ?? (leftover ? { rules: leftover.rules, key: leftover.id } : null)
  const suggestError = suggest.error instanceof ApiError ? suggest.error.detail : null

  const finish = async () => {
    setEditing(null)
    setSaved(true)
    await client.invalidateQueries({ queryKey: QUERY_KEY })
    await client.invalidateQueries({ queryKey: ['status'] })
  }
  const cancel = () => {
    setEditing(null)
    if (leftover) discard.mutate()
  }

  return (
    <section className="max-w-6xl space-y-4">
      <h1 className="text-2xl font-semibold">Search rules</h1>
      {stale && !draft && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg bg-surface p-3 text-sm">
          <span className="text-warning">
            Your profile or preferences changed since these rules were set.
          </span>
          <Button size="sm" disabled={suggest.isPending} onClick={() => suggest.mutate()}>
            Update from my profile
          </Button>
        </div>
      )}
      {draft ? (
        <RulesEditor
          key={draft.key}
          initial={draft.rules}
          fromProposal={leftover !== null}
          onSaved={finish}
          onCancel={cancel}
        />
      ) : approved ? (
        <div className="space-y-4">
          {saved && (
            <p role="status" className="text-sm text-success">
              Rules saved.
            </p>
          )}
          {approved.approved_by === 'auto' && (
            <p className="text-sm text-muted-small">
              HireTitan set these up from your profile and preferences. Change anything you like.
            </p>
          )}
          <p className="text-sm text-muted-small">
            These are the rules your searches use (version {approved.version}).
          </p>
          <ReadView rules={approved.rules} />
          <div className="flex flex-wrap gap-3">
            <Button
              onClick={() => {
                setSaved(false)
                setEditing({ rules: approved.rules, key: `edit-${approved.id}` })
              }}
            >
              <Pencil aria-hidden className="size-4" />
              Edit rules
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-muted-small">
            Rules decide which jobs are kept and which are left out. We suggest them from your
            profile and preferences; you check them and save.
          </p>
          <Button disabled={suggest.isPending} onClick={() => suggest.mutate()}>
            Suggest rules
          </Button>
        </div>
      )}
      {suggestError && (
        <p role="alert" className="text-sm text-danger">
          {suggestError}
        </p>
      )}
    </section>
  )
}
