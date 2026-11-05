import { type ReactNode } from 'react'
import { type FieldErrors, type UseFormReturn, useFieldArray } from 'react-hook-form'
import { Button } from '@/components/ui/button'
import { type ApiContent, type FormValues } from './profileForm'

type Props = {
  form: UseFormReturn<FormValues>
  /** The current profile, when this is a re-upload: changed fields show its value. */
  compare?: ApiContent | null
  changedPaths?: string[]
}

const input =
  'w-full rounded-md border border-muted-foreground bg-background px-3 py-2 text-sm'

function messageAt(errors: FieldErrors<FormValues>, path: string): string | undefined {
  let node: unknown = errors
  for (const part of path.split('.')) {
    if (node == null || typeof node !== 'object') return undefined
    node = (node as Record<string, unknown>)[part]
  }
  return (node as { message?: string } | undefined)?.message
}

function Field({
  label,
  htmlFor,
  error,
  note,
  children,
}: {
  label: string
  htmlFor: string
  error?: string
  note?: string
  children: ReactNode
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="block text-sm font-medium">
        {label}
      </label>
      {children}
      {note && <p className="text-xs text-warning">{note}</p>}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  )
}

function currentValue(compare: ApiContent | null | undefined, path: string): string | undefined {
  if (!compare) return undefined
  switch (path) {
    case 'contact.name':
      return compare.contact.name ?? ''
    case 'contact.email':
      return compare.contact.email ?? ''
    case 'contact.phone':
      return compare.contact.phone ?? ''
    case 'contact.location':
      return compare.contact.location ?? ''
    case 'headline':
      return compare.headline ?? ''
    case 'summary':
      return compare.summary ?? ''
    case 'skills':
      return (compare.skills ?? []).join(', ')
    default:
      return undefined
  }
}

function ListControls({
  index,
  count,
  onMove,
  onRemove,
  noun,
}: {
  index: number
  count: number
  onMove: (from: number, to: number) => void
  onRemove: () => void
  noun: string
}) {
  return (
    <div className="flex gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={index === 0}
        onClick={() => onMove(index, index - 1)}
        aria-label={`Move ${noun} ${index + 1} up`}
      >
        Up
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={index === count - 1}
        onClick={() => onMove(index, index + 1)}
        aria-label={`Move ${noun} ${index + 1} down`}
      >
        Down
      </Button>
      <Button
        type="button"
        variant="danger"
        size="sm"
        onClick={onRemove}
        aria-label={`Remove ${noun} ${index + 1}`}
      >
        Remove
      </Button>
    </div>
  )
}

export function ProfileFormFields({ form, compare, changedPaths = [] }: Props) {
  const { register, formState, control } = form
  const errors = formState.errors
  const experience = useFieldArray({ control, name: 'experience' })
  const education = useFieldArray({ control, name: 'education' })
  const projects = useFieldArray({ control, name: 'projects' })
  const certifications = useFieldArray({ control, name: 'certifications' })

  const noteFor = (path: string): string | undefined =>
    changedPaths.includes(path)
      ? `Changed. Current profile: ${currentValue(compare, path) || '(empty)'}`
      : undefined
  const entryChanged = (prefix: string, a: string, b: string): boolean => {
    const label = [a, b].map((s) => s.trim()).filter(Boolean).join(' | ')
    return changedPaths.some((p) => p.startsWith(`${prefix}[${label}]`))
  }

  return (
    <div className="space-y-8">
      <fieldset className="space-y-3">
        <legend className="text-lg font-semibold">Contact</legend>
        <Field label="Name" htmlFor="contact-name" error={messageAt(errors, 'contact.name')} note={noteFor('contact.name')}>
          <input id="contact-name" className={input} {...register('contact.name')} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Email" htmlFor="contact-email" error={messageAt(errors, 'contact.email')} note={noteFor('contact.email')}>
            <input id="contact-email" className={input} {...register('contact.email')} />
          </Field>
          <Field label="Phone" htmlFor="contact-phone" error={messageAt(errors, 'contact.phone')} note={noteFor('contact.phone')}>
            <input id="contact-phone" className={input} {...register('contact.phone')} />
          </Field>
        </div>
        <Field label="Location" htmlFor="contact-location" error={messageAt(errors, 'contact.location')} note={noteFor('contact.location')}>
          <input id="contact-location" className={input} {...register('contact.location')} />
        </Field>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="text-lg font-semibold">About you</legend>
        <Field label="Headline" htmlFor="headline" error={messageAt(errors, 'headline')} note={noteFor('headline')}>
          <input id="headline" className={input} {...register('headline')} />
        </Field>
        <Field label="Summary" htmlFor="summary" error={messageAt(errors, 'summary')} note={noteFor('summary')}>
          <textarea id="summary" rows={4} className={input} {...register('summary')} />
        </Field>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="text-lg font-semibold">Experience</legend>
        {experience.fields.map((field, i) => (
          <div key={field.id} className="space-y-3 rounded-lg bg-surface p-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium">
                Job {i + 1}
                {entryChanged('experience', form.getValues(`experience.${i}.employer`), form.getValues(`experience.${i}.title`)) && (
                  <span className="ml-2 rounded bg-warning px-2 py-0.5 text-xs text-background">Changed</span>
                )}
              </h3>
              <ListControls index={i} count={experience.fields.length} noun="job" onMove={experience.move} onRemove={() => experience.remove(i)} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={`Employer ${i + 1}`} htmlFor={`exp-${i}-employer`} error={messageAt(errors, `experience.${i}.employer`)}>
                <input id={`exp-${i}-employer`} className={input} {...register(`experience.${i}.employer`)} />
              </Field>
              <Field label={`Job title ${i + 1}`} htmlFor={`exp-${i}-title`} error={messageAt(errors, `experience.${i}.title`)}>
                <input id={`exp-${i}-title`} className={input} {...register(`experience.${i}.title`)} />
              </Field>
              <Field label={`Start ${i + 1}`} htmlFor={`exp-${i}-start`} error={messageAt(errors, `experience.${i}.start`)}>
                <input id={`exp-${i}-start`} placeholder="2021-03" className={input} {...register(`experience.${i}.start`)} />
              </Field>
              <Field label={`End ${i + 1}`} htmlFor={`exp-${i}-end`} error={messageAt(errors, `experience.${i}.end`)}>
                <input id={`exp-${i}-end`} placeholder="2023-06" className={input} {...register(`experience.${i}.end`)} />
              </Field>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" {...register(`experience.${i}.current`)} />
              I currently work here
            </label>
            <Field label={`Bullet points ${i + 1} (one per line)`} htmlFor={`exp-${i}-bullets`} error={messageAt(errors, `experience.${i}.bullets`)}>
              <textarea id={`exp-${i}-bullets`} rows={4} className={input} {...register(`experience.${i}.bullets`)} />
            </Field>
          </div>
        ))}
        <Button type="button" variant="outline" className="w-full border-dashed" onClick={() => experience.append({ employer: '', title: '', location: '', start: '', end: '', current: false, bullets: '' })}>
          Add a job
        </Button>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="text-lg font-semibold">Education</legend>
        {education.fields.map((field, i) => (
          <div key={field.id} className="space-y-3 rounded-lg bg-surface p-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium">
                Education {i + 1}
                {entryChanged('education', form.getValues(`education.${i}.institution`), form.getValues(`education.${i}.qualification`)) && (
                  <span className="ml-2 rounded bg-warning px-2 py-0.5 text-xs text-background">Changed</span>
                )}
              </h3>
              <ListControls index={i} count={education.fields.length} noun="education" onMove={education.move} onRemove={() => education.remove(i)} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={`Institution ${i + 1}`} htmlFor={`edu-${i}-institution`} error={messageAt(errors, `education.${i}.institution`)}>
                <input id={`edu-${i}-institution`} className={input} {...register(`education.${i}.institution`)} />
              </Field>
              <Field label={`Qualification ${i + 1}`} htmlFor={`edu-${i}-qualification`} error={messageAt(errors, `education.${i}.qualification`)}>
                <input id={`edu-${i}-qualification`} className={input} {...register(`education.${i}.qualification`)} />
              </Field>
              <Field label={`Education start ${i + 1}`} htmlFor={`edu-${i}-start`} error={messageAt(errors, `education.${i}.start`)}>
                <input id={`edu-${i}-start`} placeholder="2013" className={input} {...register(`education.${i}.start`)} />
              </Field>
              <Field label={`Education end ${i + 1}`} htmlFor={`edu-${i}-end`} error={messageAt(errors, `education.${i}.end`)}>
                <input id={`edu-${i}-end`} placeholder="2017" className={input} {...register(`education.${i}.end`)} />
              </Field>
            </div>
          </div>
        ))}
        <Button type="button" variant="outline" className="w-full border-dashed" onClick={() => education.append({ institution: '', qualification: '', field: '', start: '', end: '', grade: '' })}>
          Add education
        </Button>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="text-lg font-semibold">Skills</legend>
        <Field label="Skills (one per line)" htmlFor="skills" error={messageAt(errors, 'skills')} note={noteFor('skills')}>
          <textarea id="skills" rows={6} className={input} {...register('skills')} />
        </Field>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="text-lg font-semibold">Projects</legend>
        {projects.fields.map((field, i) => (
          <div key={field.id} className="space-y-3 rounded-lg bg-surface p-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium">Project {i + 1}</h3>
              <ListControls index={i} count={projects.fields.length} noun="project" onMove={projects.move} onRemove={() => projects.remove(i)} />
            </div>
            <Field label={`Project name ${i + 1}`} htmlFor={`proj-${i}-name`} error={messageAt(errors, `projects.${i}.name`)}>
              <input id={`proj-${i}-name`} className={input} {...register(`projects.${i}.name`)} />
            </Field>
            <Field label={`Project description ${i + 1}`} htmlFor={`proj-${i}-description`} error={messageAt(errors, `projects.${i}.description`)}>
              <textarea id={`proj-${i}-description`} rows={3} className={input} {...register(`projects.${i}.description`)} />
            </Field>
          </div>
        ))}
        <Button type="button" variant="outline" className="w-full border-dashed" onClick={() => projects.append({ name: '', description: '', technologies: '', link: '' })}>
          Add a project
        </Button>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="text-lg font-semibold">Certifications</legend>
        {certifications.fields.map((field, i) => (
          <div key={field.id} className="space-y-3 rounded-lg bg-surface p-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium">Certification {i + 1}</h3>
              <ListControls index={i} count={certifications.fields.length} noun="certification" onMove={certifications.move} onRemove={() => certifications.remove(i)} />
            </div>
            <Field label={`Certification name ${i + 1}`} htmlFor={`cert-${i}-name`} error={messageAt(errors, `certifications.${i}.name`)}>
              <input id={`cert-${i}-name`} className={input} {...register(`certifications.${i}.name`)} />
            </Field>
          </div>
        ))}
        <Button type="button" variant="outline" className="w-full border-dashed" onClick={() => certifications.append({ name: '', issuer: '', date: '' })}>
          Add a certification
        </Button>
      </fieldset>
    </div>
  )
}
