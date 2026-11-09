import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type ReactNode, useState } from 'react'
import { ApiError, apiFetch } from '@/api/client'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'

type RuleSet = components['schemas']['RuleSetOut']
type Rules = components['schemas']['SearchRulesModel-Output']
type RuleItem = components['schemas']['RuleItemModel']
type PlaceRule = components['schemas']['PlaceRuleModel']
type RulesState = components['schemas']['RulesStateOut']

const QUERY_KEY = ['search-rules'] as const
const input = 'rounded-md border border-muted-foreground bg-background px-3 py-1.5 text-sm'

/** Where a rule came from, in words the person knows (FR-002). */
function originLabel(origin: string): string {
  if (origin.startsWith('preference:')) return 'From your preferences'
  if (origin.startsWith('profile:')) return 'From your profile'
  if (origin === 'synonym_table') return 'Similar title'
  return 'Added by you'
}

/** What a rule does to a job (FR-005). */
function effectLabel(effect: string | null | undefined): string {
  return effect === 'skips' ? 'Skips jobs' : 'Guides the AI'
}

function Badge({ children, tone }: { children: ReactNode; tone: 'skips' | 'guides' | 'origin' }) {
  const colour =
    tone === 'skips' ? 'text-warning' : tone === 'guides' ? 'text-link' : 'text-muted-small'
  return <span className={`text-xs ${colour}`}>{children}</span>
}

function Section({
  title,
  hint,
  error,
  children,
}: {
  title: string
  hint?: string
  error?: string
  children: ReactNode
}) {
  return (
    <section aria-label={title} className="space-y-2 rounded-lg bg-surface p-4">
      <h2 className="text-base font-semibold">{title}</h2>
      {hint && <p className="text-sm text-muted-small">{hint}</p>}
      {children}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </section>
  )
}

function ItemRow({
  text,
  origin,
  effect,
  onRemove,
}: {
  text: string
  origin: string
  effect: string | null | undefined
  onRemove?: () => void
}) {
  return (
    <li className="flex flex-wrap items-center gap-3">
      <span className="font-medium">{text}</span>
      <Badge tone="origin">{originLabel(origin)}</Badge>
      <Badge tone={effect === 'skips' ? 'skips' : 'guides'}>{effectLabel(effect)}</Badge>
      {onRemove && (
        <Button type="button" variant="ghost" size="xs" aria-label={`Remove ${text}`} onClick={onRemove}>
          Remove
        </Button>
      )}
    </li>
  )
}

function WordList({
  title,
  hint,
  items,
  effect,
  addLabel,
  addButton,
  error,
  onChange,
}: {
  title: string
  hint?: string
  items: RuleItem[]
  effect: 'skips' | 'guides_ai'
  addLabel: string
  addButton: string
  error?: string
  onChange?: (items: RuleItem[]) => void
}) {
  const [draft, setDraft] = useState('')
  const add = () => {
    const text = draft.trim()
    if (!text || !onChange) return
    onChange([...items, { text, origin: 'user' }])
    setDraft('')
  }
  return (
    <Section title={title} hint={hint} error={error}>
      {items.length === 0 && <p className="text-sm text-muted-small">None.</p>}
      <ul className="space-y-1">
        {items.map((item, index) => (
          <ItemRow
            key={`${item.text}-${index}`}
            text={item.text}
            origin={item.origin ?? 'user'}
            effect={item.effect ?? effect}
            onRemove={onChange && (() => onChange(items.filter((_, i) => i !== index)))}
          />
        ))}
      </ul>
      {onChange && (
        <div className="flex gap-2">
          <input
            aria-label={addLabel}
            className={input}
            value={draft}
            maxLength={60}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                add()
              }
            }}
          />
          <Button type="button" variant="outline" onClick={add}>
            {addButton}
          </Button>
        </div>
      )}
    </Section>
  )
}

function placeText(place: PlaceRule): string {
  return [place.city, place.country].filter(Boolean).join(', ')
}

function PlaceList({
  title,
  hint,
  items,
  effect,
  addButton,
  error,
  onChange,
}: {
  title: string
  hint?: string
  items: PlaceRule[]
  effect: 'skips' | 'guides_ai'
  addButton: string
  error?: string
  onChange?: (items: PlaceRule[]) => void
}) {
  const [city, setCity] = useState('')
  const [country, setCountry] = useState('')
  const add = () => {
    const place = { city: city.trim() || null, country: country.trim().toUpperCase() || null }
    if (!place.city && !place.country) return
    onChange?.([...items, { ...place, origin: 'user' }])
    setCity('')
    setCountry('')
  }
  return (
    <Section title={title} hint={hint} error={error}>
      {items.length === 0 && <p className="text-sm text-muted-small">None.</p>}
      <ul className="space-y-1">
        {items.map((place, index) => (
          <ItemRow
            key={`${placeText(place)}-${index}`}
            text={placeText(place)}
            origin={place.origin ?? 'user'}
            effect={place.effect ?? effect}
            onRemove={onChange && (() => onChange(items.filter((_, i) => i !== index)))}
          />
        ))}
      </ul>
      {onChange && (
        <div className="flex flex-wrap gap-2">
          <input
            aria-label={`${title}: city`}
            placeholder="City"
            className={input}
            value={city}
            onChange={(event) => setCity(event.target.value)}
          />
          <input
            aria-label={`${title}: country code`}
            placeholder="Country (IN)"
            className={`${input} w-32`}
            maxLength={2}
            value={country}
            onChange={(event) => setCountry(event.target.value)}
          />
          <Button type="button" variant="outline" onClick={add}>
            {addButton}
          </Button>
        </div>
      )}
    </Section>
  )
}

function Summary({ rules }: { rules: Rules }) {
  const parts = [
    rules.work_modes.length ? `Work modes: ${rules.work_modes.join(', ')}` : null,
    rules.seniority.length ? `Seniority: ${rules.seniority.join(', ')}` : null,
    rules.years_experience ? `Years of experience: ${rules.years_experience}` : null,
  ].filter(Boolean)
  if (parts.length === 0) return null
  return (
    <p className="text-sm text-muted-small">
      {parts.join(' · ')} (these guide the AI; change them in Preferences)
    </p>
  )
}

function RulesView({
  rules,
  errors,
  onChange,
}: {
  rules: Rules
  errors?: ApiError | null
  onChange?: (rules: Rules) => void
}) {
  const set = <K extends keyof Rules>(key: K, value: Rules[K]) => onChange?.({ ...rules, [key]: value })
  const editable = onChange !== undefined
  const fieldError = (name: string) => errors?.fieldError(name)
  return (
    <div className="space-y-4">
      <WordList
        title="Job titles"
        hint="A job is skipped when its title matches none of these."
        items={rules.title_words}
        effect="skips"
        addLabel="Add a job title"
        addButton="Add job title"
        error={fieldError('title_words')}
        onChange={editable ? (value) => set('title_words', value) : undefined}
      />
      <WordList
        title="Words to avoid in titles"
        hint="A job is skipped when its title contains one of these."
        items={rules.title_avoid}
        effect="skips"
        addLabel="Add a word to avoid"
        addButton="Add avoid word"
        error={fieldError('title_avoid')}
        onChange={editable ? (value) => set('title_avoid', value) : undefined}
      />
      <PlaceList
        title="Places to skip"
        hint="Jobs in these places are skipped."
        items={rules.blocked_locations}
        effect="skips"
        addButton="Add place to skip"
        error={fieldError('blocked_locations')}
        onChange={editable ? (value) => set('blocked_locations', value) : undefined}
      />
      <Section title="How old a job may be" error={fieldError('max_age_days')}>
        <label className="flex items-center gap-2 text-sm">
          Skip jobs posted more than
          <input
            type="number"
            min={1}
            max={365}
            className={`${input} w-24`}
            value={rules.max_age_days}
            disabled={!editable}
            onChange={(event) => set('max_age_days', Number(event.target.value))}
          />
          days ago
        </label>
        <p className="text-xs text-muted-small">A job with no date is never skipped for its age.</p>
      </Section>
      <WordList
        title="Skills"
        hint="The AI uses these to judge whether a job suits you."
        items={rules.stack_keywords}
        effect="guides_ai"
        addLabel="Add a skill"
        addButton="Add skill"
        error={fieldError('stack_keywords')}
        onChange={editable ? (value) => set('stack_keywords', value) : undefined}
      />
      <PlaceList
        title="Places you prefer"
        items={rules.preferred_locations}
        effect="guides_ai"
        addButton="Add preferred place"
        error={fieldError('preferred_locations')}
        onChange={editable ? (value) => set('preferred_locations', value) : undefined}
      />
      <Summary rules={rules} />
    </div>
  )
}

function ProposalEditor({
  proposal,
  onApproved,
}: {
  proposal: RuleSet
  onApproved: () => void
}) {
  const client = useQueryClient()
  const [draft, setDraft] = useState<Rules>(proposal.rules)

  const approve = useMutation({
    mutationFn: async () => {
      await apiFetch<RuleSet>('/search/rules/proposal', { method: 'PUT', json: draft })
      return apiFetch<RuleSet>('/search/rules/proposal/approve', { method: 'POST' })
    },
    onSuccess: async () => {
      onApproved()
      await client.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })
  const discard = useMutation({
    mutationFn: () => apiFetch('/search/rules/proposal', { method: 'DELETE' }),
    onSuccess: () => client.invalidateQueries({ queryKey: QUERY_KEY }),
  })
  const error = approve.error instanceof ApiError ? approve.error : null

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-small">
        Proposed from your profile and preferences. Change anything, then approve. Nothing is
        searched until you approve.
      </p>
      <RulesView rules={draft} errors={error} onChange={setDraft} />
      {error && error.fieldErrors.length === 0 && (
        <p role="alert" className="text-sm text-danger">
          {error.detail}
        </p>
      )}
      <div className="flex gap-3">
        <Button variant="success" disabled={approve.isPending} onClick={() => approve.mutate()}>
          Approve
        </Button>
        <Button variant="danger" disabled={discard.isPending} onClick={() => discard.mutate()}>
          Discard
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
  const [justApproved, setJustApproved] = useState(false)
  const propose = useMutation({
    mutationFn: () => apiFetch<RuleSet>('/search/rules/proposal', { method: 'POST' }),
    onSuccess: () => {
      setJustApproved(false)
      return client.invalidateQueries({ queryKey: QUERY_KEY })
    },
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
  const proposeError = propose.error instanceof ApiError ? propose.error.detail : null

  return (
    <section className="max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold">Search rules</h1>
      {stale && !proposal && (
        <p className="rounded-lg bg-surface p-3 text-sm text-warning">
          Your profile or preferences changed since you approved these rules.
        </p>
      )}
      {proposal ? (
        <ProposalEditor key={proposal.id} proposal={proposal} onApproved={() => setJustApproved(true)} />
      ) : (
        <div className="space-y-4">
          {approved ? (
            <>
              {justApproved && <p className="text-sm text-success">Rules approved.</p>}
              <p className="text-sm text-muted-small">
                These are the rules your searches use (version {approved.version}).
              </p>
              <RulesView rules={approved.rules} />
            </>
          ) : (
            <p className="text-sm text-muted-small">
              Rules decide which jobs are skipped for free and which are shown. We propose them from
              your profile and preferences; you check and approve them.
            </p>
          )}
          {proposeError && (
            <p role="alert" className="text-sm text-danger">
              {proposeError}
            </p>
          )}
          <Button disabled={propose.isPending} onClick={() => propose.mutate()}>
            {approved ? 'Propose new rules' : 'Propose rules'}
          </Button>
        </div>
      )}
    </section>
  )
}
