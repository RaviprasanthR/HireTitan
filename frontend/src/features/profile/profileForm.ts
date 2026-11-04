import { z } from 'zod'
import type { components } from '@/api/schema'

export type ApiContent = components['schemas']['ProfileContentModel']

/** "2021-03" or "2021" or "" (empty = no date). */
const dateText = z
  .string()
  .max(7)
  .refine((v) => v === '' || /^(19[5-9]\d|20\d\d|2100)(-(0[1-9]|1[0-2]))?$/.test(v), {
    message: 'Use a year or year-month, like 2021 or 2021-03',
  })

const text = (max: number) => z.string().max(max, `At most ${max} characters`)

const lines = (maxItems: number, maxLen: number, what: string) =>
  z.string().superRefine((value, ctx) => {
    const items = splitLines(value)
    if (items.length > maxItems) ctx.addIssue({ code: 'custom', message: `At most ${maxItems} ${what}` })
    if (items.some((i) => i.length > maxLen)) {
      ctx.addIssue({ code: 'custom', message: `Each entry can be at most ${maxLen} characters` })
    }
  })

export const formSchema = z.object({
  contact: z.object({
    name: text(120),
    email: text(254),
    phone: text(40),
    location: text(120),
    links: z
      .array(z.object({ url: text(500), label: text(100) }))
      .max(10, 'At most 10 links'),
  }),
  headline: text(200),
  summary: text(2000),
  experience: z
    .array(
      z.object({
        id: z.string().optional(),
        employer: text(200),
        title: text(200),
        location: text(120),
        start: dateText,
        end: dateText,
        current: z.boolean(),
        bullets: lines(30, 500, 'bullet points'),
      }),
    )
    .max(40, 'At most 40 jobs'),
  education: z
    .array(
      z.object({
        id: z.string().optional(),
        institution: text(200),
        qualification: text(200),
        field: text(200),
        start: dateText,
        end: dateText,
        grade: text(50),
      }),
    )
    .max(20, 'At most 20 entries'),
  skills: lines(150, 80, 'skills'),
  projects: z
    .array(
      z.object({
        id: z.string().optional(),
        name: text(200),
        description: text(1000),
        technologies: lines(30, 80, 'technologies'),
        link: text(500),
      }),
    )
    .max(30, 'At most 30 projects'),
  certifications: z
    .array(
      z.object({
        id: z.string().optional(),
        name: text(200),
        issuer: text(200),
        date: dateText,
      }),
    )
    .max(30, 'At most 30 certifications'),
})

export type FormValues = z.infer<typeof formSchema>

export const splitLines = (value: string): string[] =>
  value
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)

const orNull = (v: string): string | null => (v.trim() === '' ? null : v)

function ymToText(ym: { year: number; month?: number | null } | null | undefined): string {
  if (!ym) return ''
  return ym.month ? `${ym.year}-${String(ym.month).padStart(2, '0')}` : String(ym.year)
}

function textToYm(v: string): { year: number; month: number | null } | null {
  if (!v) return null
  const [year, month] = v.split('-')
  return { year: Number(year), month: month ? Number(month) : null }
}

export function toFormValues(c: ApiContent): FormValues {
  return {
    contact: {
      name: c.contact.name ?? '',
      email: c.contact.email ?? '',
      phone: c.contact.phone ?? '',
      location: c.contact.location ?? '',
      links: (c.contact.links ?? []).map((l) => ({ url: l.url, label: l.label ?? '' })),
    },
    headline: c.headline ?? '',
    summary: c.summary ?? '',
    experience: (c.experience ?? []).map((e) => ({
      id: e.id ?? undefined,
      employer: e.employer ?? '',
      title: e.title ?? '',
      location: e.location ?? '',
      start: ymToText(e.start),
      end: ymToText(e.end),
      current: e.current ?? false,
      bullets: (e.bullets ?? []).join('\n'),
    })),
    education: (c.education ?? []).map((e) => ({
      id: e.id ?? undefined,
      institution: e.institution ?? '',
      qualification: e.qualification ?? '',
      field: e.field ?? '',
      start: ymToText(e.start),
      end: ymToText(e.end),
      grade: e.grade ?? '',
    })),
    skills: (c.skills ?? []).join('\n'),
    projects: (c.projects ?? []).map((p) => ({
      id: p.id ?? undefined,
      name: p.name ?? '',
      description: p.description ?? '',
      technologies: (p.technologies ?? []).join('\n'),
      link: p.link ?? '',
    })),
    certifications: (c.certifications ?? []).map((x) => ({
      id: x.id ?? undefined,
      name: x.name ?? '',
      issuer: x.issuer ?? '',
      date: ymToText(x.date),
    })),
  }
}

export function toApiContent(v: FormValues): ApiContent {
  return {
    contact: {
      name: v.contact.name,
      email: orNull(v.contact.email),
      phone: orNull(v.contact.phone),
      location: orNull(v.contact.location),
      links: v.contact.links
        .filter((l) => l.url.trim())
        .map((l) => ({ url: l.url, label: orNull(l.label) })),
    },
    headline: orNull(v.headline),
    summary: orNull(v.summary),
    experience: v.experience.map((e) => ({
      id: e.id ?? null,
      employer: e.employer,
      title: e.title,
      location: orNull(e.location),
      start: textToYm(e.start),
      end: e.current ? null : textToYm(e.end),
      current: e.current,
      bullets: splitLines(e.bullets),
    })),
    education: v.education.map((e) => ({
      id: e.id ?? null,
      institution: e.institution,
      qualification: orNull(e.qualification),
      field: orNull(e.field),
      start: textToYm(e.start),
      end: textToYm(e.end),
      grade: orNull(e.grade),
    })),
    skills: splitLines(v.skills),
    projects: v.projects.map((p) => ({
      id: p.id ?? null,
      name: p.name,
      description: orNull(p.description),
      technologies: splitLines(p.technologies),
      link: orNull(p.link),
    })),
    certifications: v.certifications.map((c) => ({
      id: c.id ?? null,
      name: c.name,
      issuer: orNull(c.issuer),
      date: textToYm(c.date),
    })),
  }
}

/** Server paths like ``experience[0].end`` become form paths like ``experience.0.end``. */
export const toFormPath = (path: string): string => path.replace(/\[(\d+)\]/g, '.$1')

export const emptyContent: ApiContent = {
  contact: { name: '', links: [] },
  experience: [],
  education: [],
  skills: [],
  projects: [],
  certifications: [],
}
