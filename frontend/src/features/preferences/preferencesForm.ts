import { z } from 'zod'
import type { components } from '@/api/schema'

export type ApiPreferences = components['schemas']['PreferencesModel-Input']
export type StoredPreferences = components['schemas']['PreferencesModel-Output']
export type Place = { city: string; country: string }

export const SENIORITY = [
  ['intern', 'Intern'],
  ['entry', 'Entry'],
  ['junior', 'Junior'],
  ['mid', 'Mid'],
  ['senior', 'Senior'],
  ['lead', 'Lead'],
  ['staff', 'Staff'],
  ['principal', 'Principal'],
  ['manager', 'Manager'],
  ['director', 'Director'],
] as const
export const WORK_MODES = [
  ['onsite', 'On-site'],
  ['hybrid', 'Hybrid'],
  ['remote', 'Remote'],
] as const
export const JOB_TYPES = [
  ['full_time', 'Full-time'],
  ['contract', 'Contract'],
  ['internship', 'Internship'],
] as const

const LAKH = 100_000

const strings = (what: string, maxItems: number, maxLen: number) =>
  z
    .array(z.string())
    .max(maxItems, `At most ${maxItems} ${what}`)
    .refine((items) => items.every((i) => i.length <= maxLen), {
      message: `Each entry can be at most ${maxLen} characters`,
    })

const place = z.object({ city: z.string().max(120), country: z.string().length(2) })

const money = z.string().refine((v) => v.trim() === '' || (isNumber(v) && Number(v) >= 0), {
  message: 'Enter an amount of zero or more',
})

function isNumber(v: string): boolean {
  return v.trim() !== '' && Number.isFinite(Number(v))
}

export const formSchema = z
  .object({
    target_roles: strings('roles', 20, 100).min(1, 'Add at least one target role'),
    seniority_levels: z.array(z.string()),
    years_experience: z.string().refine(
      (v) => {
        if (v.trim() === '') return true
        const n = Number(v)
        return isNumber(v) && n >= 0 && n <= 60 && (n * 2) % 1 === 0
      },
      { message: 'Enter 0 to 60 years, in steps of half a year' },
    ),
    key_skills: strings('skills', 50, 80),
    preferred_locations: z.array(place).max(20, 'At most 20 locations'),
    default_country: z.string().length(2, 'Choose a country'),
    work_modes: z.array(z.string()).min(1, 'Choose at least one work mode'),
    willing_to_relocate: z.boolean(),
    blocked_locations: z.array(place).max(50, 'At most 50 locations'),
    job_types: z.array(z.string()).min(1, 'Choose at least one job type'),
    currency: z.string().length(3, 'Choose a currency'),
    min_pay: money,
    target_pay: money,
    basis: z.enum(['fixed', 'total']),
    notice_mode: z.enum(['notice', 'date']),
    notice_period_days: z.string(),
    earliest_start_date: z.string(),
    preferred_companies: strings('companies', 100, 200),
    avoided_companies: strings('companies', 100, 200),
  })
  .superRefine((v, ctx) => {
    if (isNumber(v.min_pay) && isNumber(v.target_pay) && Number(v.min_pay) > Number(v.target_pay)) {
      ctx.addIssue({
        code: 'custom',
        path: ['min_pay'],
        message: 'Minimum pay cannot be above the target',
      })
    }
    if (v.notice_mode === 'notice' && v.notice_period_days.trim() !== '') {
      const n = Number(v.notice_period_days)
      if (!Number.isInteger(n) || n < 0 || n > 365) {
        ctx.addIssue({
          code: 'custom',
          path: ['notice_period_days'],
          message: 'Notice period must be 0 to 365 days',
        })
      }
    }
  })

export type FormValues = z.infer<typeof formSchema>

/** Pay is typed in lakh per annum (LPA) for INR and as a yearly amount otherwise. */
export const isLpa = (currency: string) => currency === 'INR'

function toDisplay(annual: string | null | undefined, currency: string): string {
  if (annual == null || annual === '') return ''
  return isLpa(currency) ? String(Number(annual) / LAKH) : String(Number(annual))
}

function toAnnual(shown: string, currency: string): string | null {
  const text = shown.trim()
  if (text === '') return null
  // Whole paise of an LPA figure, so 18.5 LPA is exactly 1850000 and never 1849999.999.
  return isLpa(currency) ? String(Math.round(Number(text) * 100) * 1000) : String(Number(text))
}

export function toFormValues(p: StoredPreferences): FormValues {
  const places = (list: { city?: string | null; country: string }[]) =>
    list.map((x) => ({ city: x.city ?? '', country: x.country }))
  return {
    target_roles: p.target_roles,
    seniority_levels: p.seniority_levels,
    years_experience: p.years_experience == null ? '' : String(Number(p.years_experience)),
    key_skills: p.key_skills,
    preferred_locations: places(p.preferred_locations),
    default_country: p.default_country,
    work_modes: p.work_modes,
    willing_to_relocate: p.willing_to_relocate,
    blocked_locations: places(p.blocked_locations),
    job_types: p.job_types,
    currency: p.pay.currency,
    min_pay: toDisplay(p.pay.min_annual, p.pay.currency),
    target_pay: toDisplay(p.pay.target_annual, p.pay.currency),
    basis: p.pay.basis === 'total' ? 'total' : 'fixed',
    notice_mode: p.earliest_start_date ? 'date' : 'notice',
    notice_period_days: p.notice_period_days == null ? '' : String(p.notice_period_days),
    earliest_start_date: p.earliest_start_date ?? '',
    preferred_companies: p.preferred_companies,
    avoided_companies: p.avoided_companies,
  }
}

export function toApi(v: FormValues): ApiPreferences {
  const places = (list: Place[]) =>
    list.map((x) => ({ city: x.city.trim() === '' ? null : x.city.trim(), country: x.country }))
  const byDate = v.notice_mode === 'date'
  return {
    target_roles: v.target_roles,
    seniority_levels: v.seniority_levels,
    years_experience: v.years_experience.trim() === '' ? null : String(Number(v.years_experience)),
    key_skills: v.key_skills,
    preferred_locations: places(v.preferred_locations),
    default_country: v.default_country,
    work_modes: v.work_modes,
    willing_to_relocate: v.willing_to_relocate,
    blocked_locations: places(v.blocked_locations),
    job_types: v.job_types,
    pay: {
      currency: v.currency,
      min_annual: toAnnual(v.min_pay, v.currency),
      target_annual: toAnnual(v.target_pay, v.currency),
      basis: v.basis,
    },
    notice_period_days: byDate || v.notice_period_days.trim() === '' ? null : Number(v.notice_period_days),
    earliest_start_date: byDate && v.earliest_start_date !== '' ? v.earliest_start_date : null,
    preferred_companies: v.preferred_companies,
    avoided_companies: v.avoided_companies,
  }
}

const SERVER_FIELD: Record<string, keyof FormValues> = {
  'pay.min_annual': 'min_pay',
  'pay.target_annual': 'target_pay',
  'pay.currency': 'currency',
  'pay.basis': 'basis',
}

/** Maps a server field path ("pay.min_annual") to the form field that shows it. */
export function toFormField(path: string): keyof FormValues | null {
  const field = SERVER_FIELD[path] ?? path.split(/[.[]/)[0] ?? ''
  return field in formSchema.shape ? (field as keyof FormValues) : null
}
