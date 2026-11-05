import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { type ReactNode, useState } from 'react'
import { Controller, type UseFormReturn, useForm, useWatch } from 'react-hook-form'
import { ApiError, apiFetch } from '@/api/client'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'
import { ChipInput } from './ChipInput'
import { COUNTRIES, CURRENCIES } from './iso'
import { PlacesInput } from './PlacesInput'
import {
  type FormValues,
  JOB_TYPES,
  SENIORITY,
  WORK_MODES,
  formSchema,
  isLpa,
  toApi,
  toFormField,
  toFormValues,
} from './preferencesForm'

type PreferencesOut = components['schemas']['PreferencesOut']

const input = 'w-full rounded-md border border-muted-foreground bg-background px-3 py-2 text-sm'

function Field({
  name,
  label,
  htmlFor,
  hint,
  form,
  children,
}: {
  name: keyof FormValues
  label: string
  htmlFor: string
  hint?: string
  form: UseFormReturn<FormValues>
  children: ReactNode
}) {
  const error = form.formState.errors[name]?.message as string | undefined
  return (
    <div className="space-y-1" data-testid={`field-${name}`}>
      <label htmlFor={htmlFor} className="block text-sm font-medium">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-muted-small">{hint}</p>}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  )
}

/** A group of checkboxes that stores the ticked values as a list. */
function Choices({
  name,
  legend,
  options,
  form,
}: {
  name: 'work_modes' | 'job_types' | 'seniority_levels'
  legend: string
  options: readonly (readonly [string, string])[]
  form: UseFormReturn<FormValues>
}) {
  const error = form.formState.errors[name]?.message as string | undefined
  return (
    <fieldset className="space-y-1" data-testid={`field-${name}`}>
      <legend className="text-sm font-medium">{legend}</legend>
      <Controller
        control={form.control}
        name={name}
        render={({ field }) => (
          <div className="flex flex-wrap gap-4">
            {options.map(([value, text]) => (
              <label key={value} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={field.value.includes(value)}
                  onChange={(e) =>
                    field.onChange(
                      e.target.checked
                        ? [...field.value, value]
                        : field.value.filter((v) => v !== value),
                    )
                  }
                />
                {text}
              </label>
            ))}
          </div>
        )}
      />
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </fieldset>
  )
}

function Suggestions({
  label,
  ideas,
  chosen,
  onAdd,
}: {
  label: string
  ideas: string[]
  chosen: string[]
  onAdd: (idea: string) => void
}) {
  const taken = new Set(chosen.map((c) => c.trim().toLocaleLowerCase()))
  const open = ideas.filter((i) => !taken.has(i.trim().toLocaleLowerCase()))
  if (open.length === 0) return null
  return (
    <div
      role="group"
      className="flex flex-wrap items-center gap-2"
      aria-label={`${label} from your profile`}
    >
      <span className="text-xs text-muted-small">From your profile:</span>
      {open.map((idea) => (
        <Button
          key={idea}
          type="button"
          size="xs"
          variant="outline"
          aria-label={`Add '${idea}'`}
          onClick={() => onAdd(idea)}
        >
          + {idea}
        </Button>
      ))}
    </div>
  )
}

type EmbeddedProps = {
  /** Inside the setup card: the card has the heading, and the button finishes setup. */
  embedded?: boolean
  /** Called after a successful save when embedded; may throw to show a message. */
  onSaved?: () => Promise<void>
}

function PreferencesForm({
  data,
  embedded = false,
  onSaved,
}: { data: PreferencesOut } & EmbeddedProps) {
  const queryClient = useQueryClient()
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: toFormValues(data.content),
  })
  const [savedAt, setSavedAt] = useState<string | null>(data.saved_at ?? null)
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const { control } = form
  const currency = useWatch({ control, name: 'currency' })
  const mode = useWatch({ control, name: 'notice_mode' })
  const chosenRoles = useWatch({ control, name: 'target_roles' })
  const chosenSkills = useWatch({ control, name: 'key_skills' })
  const country = useWatch({ control, name: 'default_country' })
  const payUnit = isLpa(currency) ? 'LPA' : 'per year'

  async function save(values: FormValues) {
    setFormError(null)
    setBusy(true)
    try {
      const saved = await apiFetch<{ saved_at: string }>('/preferences', {
        method: 'PUT',
        json: toApi(values),
      })
      setSavedAt(saved.saved_at)
      await queryClient.invalidateQueries({ queryKey: ['preferences'], refetchType: 'none' })
      await onSaved?.()
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && e.fieldErrors.length > 0) {
        for (const err of e.fieldErrors) {
          const field = toFormField(err.field)
          if (field) form.setError(field, { type: 'server', message: err.message })
          else setFormError(err.message)
        }
      } else {
        setFormError(e instanceof ApiError ? e.detail : 'Something went wrong. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  const addTo = (name: 'target_roles' | 'key_skills') => (idea: string) =>
    form.setValue(name, [...form.getValues(name), idea], { shouldDirty: true })

  return (
    <form onSubmit={form.handleSubmit(save)} className="max-w-3xl space-y-8" noValidate>
      {!embedded && (
        <div>
          <h1 className="text-2xl font-semibold">Preferences</h1>
          <p className="text-sm text-muted-small" aria-live="polite">
            {savedAt ? `Last saved ${new Date(savedAt).toLocaleString()}` : 'Not saved yet'}
          </p>
        </div>
      )}

      <section className="space-y-4">
        <h2 className="text-lg font-medium">What you are looking for</h2>
        <Field
          name="target_roles"
          label="Target roles"
          htmlFor="target_roles"
          form={form}
          hint="Type a role and press Enter."
        >
          <Controller
            control={form.control}
            name="target_roles"
            render={({ field }) => (
              <ChipInput id="target_roles" value={field.value} onChange={field.onChange} />
            )}
          />
          <Suggestions
            label="Roles"
            ideas={data.suggestions.target_roles ?? []}
            chosen={chosenRoles}
            onAdd={addTo('target_roles')}
          />
        </Field>
        <Choices name="seniority_levels" legend="Seniority" options={SENIORITY} form={form} />
        <Field
          name="years_experience"
          label="Years of experience"
          htmlFor="years_experience"
          form={form}
          hint="Optional. You type this; it is never taken from your resume."
        >
          <input
            id="years_experience"
            type="number"
            step="0.5"
            min="0"
            className={`${input} max-w-40`}
            {...form.register('years_experience')}
          />
        </Field>
        <Field name="key_skills" label="Key skills" htmlFor="key_skills" form={form}>
          <Controller
            control={form.control}
            name="key_skills"
            render={({ field }) => (
              <ChipInput id="key_skills" value={field.value} onChange={field.onChange} />
            )}
          />
          <Suggestions
            label="Skills"
            ideas={data.suggestions.key_skills ?? []}
            chosen={chosenSkills}
            onAdd={addTo('key_skills')}
          />
        </Field>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Where and how</h2>
        <Field
          name="default_country"
          label="Default country"
          htmlFor="default_country"
          form={form}
          hint="Used to read phone numbers written without a country code."
        >
          <select
            id="default_country"
            className={`${input} max-w-xs`}
            {...form.register('default_country')}
          >
            {COUNTRIES.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
        <div data-testid="field-preferred_locations" className="space-y-1">
          <p className="text-sm font-medium">Preferred locations</p>
          <Controller
            control={form.control}
            name="preferred_locations"
            render={({ field }) => (
              <PlacesInput
                label="Preferred location"
                value={field.value}
                onChange={field.onChange}
                defaultCountry={country}
              />
            )}
          />
          {form.formState.errors.preferred_locations?.message && (
            <p role="alert" className="text-sm text-danger">
              {form.formState.errors.preferred_locations.message}
            </p>
          )}
        </div>
        <Choices name="work_modes" legend="Work modes" options={WORK_MODES} form={form} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" {...form.register('willing_to_relocate')} />
          Willing to relocate
        </label>
        <div data-testid="field-blocked_locations" className="space-y-1">
          <p className="text-sm font-medium">Locations to avoid</p>
          <Controller
            control={form.control}
            name="blocked_locations"
            render={({ field }) => (
              <PlacesInput
                label="Avoided location"
                value={field.value}
                onChange={field.onChange}
                defaultCountry={country}
              />
            )}
          />
          {form.formState.errors.blocked_locations?.message && (
            <p role="alert" className="text-sm text-danger">
              {form.formState.errors.blocked_locations.message}
            </p>
          )}
        </div>
        <Choices name="job_types" legend="Job types" options={JOB_TYPES} form={form} />
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Pay and timing</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field name="currency" label="Currency" htmlFor="currency" form={form}>
            <select id="currency" className={input} {...form.register('currency')}>
              {CURRENCIES.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.code} · {c.name}
                </option>
              ))}
            </select>
          </Field>
          <Field name="basis" label="Pay basis" htmlFor="basis" form={form}>
            <select id="basis" className={input} {...form.register('basis')}>
              <option value="fixed">Fixed pay</option>
              <option value="total">Total pay (with bonus)</option>
            </select>
          </Field>
          <Field name="min_pay" label={`Minimum pay (${payUnit})`} htmlFor="min_pay" form={form}>
            <input
              id="min_pay"
              inputMode="decimal"
              className={input}
              {...form.register('min_pay')}
            />
          </Field>
          <Field
            name="target_pay"
            label={`Target pay (${payUnit})`}
            htmlFor="target_pay"
            form={form}
          >
            <input
              id="target_pay"
              inputMode="decimal"
              className={input}
              {...form.register('target_pay')}
            />
          </Field>
        </div>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Availability</legend>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input type="radio" value="notice" {...form.register('notice_mode')} />I have a notice
              period
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" value="date" {...form.register('notice_mode')} />I can start on a
              date
            </label>
          </div>
          {mode === 'notice' ? (
            <Field
              name="notice_period_days"
              label="Notice period (days)"
              htmlFor="notice_period_days"
              form={form}
            >
              <input
                id="notice_period_days"
                type="number"
                min="0"
                max="365"
                className={`${input} max-w-40`}
                {...form.register('notice_period_days')}
              />
            </Field>
          ) : (
            <Field
              name="earliest_start_date"
              label="Earliest start date"
              htmlFor="earliest_start_date"
              form={form}
            >
              <input
                id="earliest_start_date"
                type="date"
                className={`${input} max-w-xs`}
                {...form.register('earliest_start_date')}
              />
            </Field>
          )}
        </fieldset>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Companies</h2>
        <Field
          name="preferred_companies"
          label="Companies you like"
          htmlFor="preferred_companies"
          form={form}
        >
          <Controller
            control={form.control}
            name="preferred_companies"
            render={({ field }) => (
              <ChipInput id="preferred_companies" value={field.value} onChange={field.onChange} />
            )}
          />
        </Field>
        <Field
          name="avoided_companies"
          label="Companies to avoid"
          htmlFor="avoided_companies"
          form={form}
        >
          <Controller
            control={form.control}
            name="avoided_companies"
            render={({ field }) => (
              <ChipInput id="avoided_companies" value={field.value} onChange={field.onChange} />
            )}
          />
        </Field>
      </section>

      {formError && (
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          {formError}
        </p>
      )}
      <Button type="submit" variant="success" disabled={busy}>
        {embedded ? 'Finish setup' : 'Save preferences'}
      </Button>
    </form>
  )
}

export function PreferencesPage(props: EmbeddedProps) {
  const query = useQuery({
    queryKey: ['preferences'],
    queryFn: () => apiFetch<PreferencesOut>('/preferences'),
    staleTime: Infinity,
    refetchOnMount: 'always', // the form starts from what is saved, never from a stale copy
    refetchOnWindowFocus: false,
  })
  if (query.isPending || query.isError) {
    return (
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">Preferences</h1>
        {query.isError ? (
          <p role="alert">Could not load your preferences.</p>
        ) : (
          <p>Loading your preferences…</p>
        )}
      </div>
    )
  }
  return <PreferencesForm data={query.data} {...props} />
}
