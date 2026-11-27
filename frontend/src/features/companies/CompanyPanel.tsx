import { Link2, Mail, Pencil, Phone, StickyNote, Trash2, Users } from 'lucide-react'
import { safeHttpUrl } from '@/lib/safeUrl'
import { useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import {
  useAddContact,
  useContacts,
  useDeleteContact,
  useEditContact,
  useSaveNote,
  type Contact,
  type ContactInput,
} from './api'
import { Field, inputClass } from './Field'
import { IconButton } from './IconButton'

const EMPTY: ContactInput = {
  name: '',
  role: '',
  linkedin_url: '',
  email: '',
  phone: '',
  confidence: '',
  note: '',
}

function valuesOf(contact: Contact): ContactInput {
  return {
    name: contact.name,
    role: contact.role ?? '',
    linkedin_url: contact.linkedin_url ?? '',
    email: contact.email ?? '',
    phone: contact.phone ?? '',
    confidence: contact.confidence ?? '',
    note: contact.note ?? '',
  }
}

const TEXT_FIELDS: { key: keyof ContactInput; label: string }[] = [
  { key: 'name', label: 'Name' },
  { key: 'role', label: 'Role' },
  { key: 'linkedin_url', label: 'LinkedIn link' },
  { key: 'email', label: 'Email' },
  { key: 'phone', label: 'Phone' },
]

/** Add or edit one contact. Only the name is required; a refused field shows its reason. */
function ContactForm({
  initial,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  initial: ContactInput
  pending: boolean
  error: unknown
  onSubmit: (values: ContactInput) => void
  onCancel: () => void
}) {
  const [values, setValues] = useState(initial)
  const apiError = error instanceof ApiError ? error : null
  const general = apiError && apiError.fieldErrors.length === 0 ? apiError.message : null
  return (
    <form
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit(values)
      }}
    >
      {TEXT_FIELDS.map(({ key, label }) => (
        <Field key={key} label={label} error={apiError?.fieldError(key)}>
          {(props) => (
            <input
              {...props}
              className={inputClass}
              value={values[key]}
              onChange={(event) => setValues({ ...values, [key]: event.target.value })}
            />
          )}
        </Field>
      ))}
      <Field label="Confidence" error={apiError?.fieldError('confidence')}>
        {(props) => (
          <select
            {...props}
            className={inputClass}
            value={values.confidence}
            onChange={(event) => setValues({ ...values, confidence: event.target.value })}
          >
            <option value="">Not set</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        )}
      </Field>
      <div className="sm:col-span-2">
        <Field label="About this person" error={apiError?.fieldError('note')}>
          {(props) => (
            <textarea
              {...props}
              rows={2}
              className={inputClass}
              value={values.note}
              onChange={(event) => setValues({ ...values, note: event.target.value })}
            />
          )}
        </Field>
      </div>
      {general && (
        <p role="alert" className="text-sm text-danger sm:col-span-2">
          {general}
        </p>
      )}
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" size="sm" disabled={pending} variant="success">
          Save contact
        </Button>
        <Button type="button" variant="cancel" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

// how sure the person is about a contact: a pill in a matching colour
const CONFIDENCE_TONE: Record<string, string> = { high: 'green', medium: 'yellow', low: 'red' }

function ContactItem({ contact, companyId }: { contact: Contact; companyId: string }) {
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const edit = useEditContact(companyId)
  const remove = useDeleteContact(companyId)

  if (editing) {
    return (
      <li className="rounded-md border border-muted-foreground p-3">
        <ContactForm
          initial={valuesOf(contact)}
          pending={edit.isPending}
          error={edit.error}
          onCancel={() => {
            edit.reset()
            setEditing(false)
          }}
          onSubmit={(values) =>
            edit.mutate({ id: contact.id, values }, { onSuccess: () => setEditing(false) })
          }
        />
      </li>
    )
  }
  return (
    <li className="space-y-2 rounded-lg border border-white/10 bg-white/[0.035] p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <p className="font-semibold text-heading">{contact.name}</p>
          {(contact.role || contact.confidence) && (
            <p className="flex flex-wrap gap-1.5">
              {contact.role && <span className="ht-pill ht-pill-grey">{contact.role}</span>}
              {contact.confidence && (
                <span
                  className={`ht-pill ht-pill-${CONFIDENCE_TONE[contact.confidence] ?? 'grey'}`}
                >
                  {contact.confidence} confidence
                </span>
              )}
            </p>
          )}
        </div>
        {!confirming && (
          <div className="flex gap-1">
            <IconButton
              title="Edit"
              label={`Edit ${contact.name}`}
              tone="text-subtle hover:bg-raised hover:text-foreground"
              onClick={() => setEditing(true)}
            >
              <Pencil aria-hidden />
            </IconButton>
            <IconButton
              title="Delete"
              label={`Delete ${contact.name}`}
              tone="text-subtle hover:bg-raised hover:text-danger"
              onClick={() => setConfirming(true)}
            >
              <Trash2 aria-hidden />
            </IconButton>
          </div>
        )}
      </div>
      {(contact.linkedin_url || contact.email || contact.phone) && (
        <div className="flex flex-wrap gap-2 text-sm">
          {contact.linkedin_url && (
            <span className="ht-fact">
              <Link2 aria-hidden className="size-4 text-stage-inquired" />
              <a
                href={safeHttpUrl(contact.linkedin_url)}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`LinkedIn profile of ${contact.name}`}
                className="text-link underline"
              >
                LinkedIn
              </a>
            </span>
          )}
          {contact.email && (
            <span className="ht-fact">
              <Mail aria-hidden className="size-4 text-warning" />
              {contact.email}
            </span>
          )}
          {contact.phone && (
            <span className="ht-fact">
              <Phone aria-hidden className="size-4 text-success" />
              {contact.phone}
            </span>
          )}
        </div>
      )}
      {contact.note && (
        <blockquote className="border-l-2 border-warning/60 pl-3 text-sm whitespace-pre-line text-foreground/90">
          {contact.note}
        </blockquote>
      )}
      {confirming && (
        <div className="space-y-2 rounded-md border border-danger/40 bg-danger/10 p-2">
          <p className="text-sm">Delete {contact.name}? This cannot be undone.</p>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              disabled={remove.isPending}
              onClick={() => remove.mutate(contact.id)}
             variant="danger">
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

function NoteEditor({
  companyId,
  companyName,
  initial,
}: {
  companyId: string
  companyName: string
  initial: string
}) {
  const [body, setBody] = useState(initial)
  const save = useSaveNote(companyId)
  const apiError = save.error instanceof ApiError ? save.error : null
  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium" htmlFor={`note-${companyId}`}>
        Note about {companyName}
      </label>
      <textarea
        id={`note-${companyId}`}
        rows={3}
        className={inputClass}
        value={body}
        onChange={(event) => setBody(event.target.value)}
      />
      {apiError && (
        <p role="alert" className="text-sm text-danger">
          {apiError.message}
        </p>
      )}
      <Button type="button" size="sm" disabled={save.isPending} onClick={() => save.mutate(body)} variant="outline">
        Save note
      </Button>
      {save.isSuccess && (
        <p role="status" className="text-sm text-muted-small">
          Note saved
        </p>
      )}
    </div>
  )
}

/** The people the person knows at a company, and one private note. All text, never sent anywhere. */
export function CompanyPanel({
  companyId,
  companyName,
}: {
  companyId: string
  companyName: string
}) {
  const panel = useContacts(companyId)
  const add = useAddContact(companyId)
  const [adding, setAdding] = useState(false)

  if (panel.isPending) return <p>Loading…</p>
  if (panel.isError) return <p role="alert">Could not load the contacts.</p>
  const { items, note } = panel.data
  return (
    <section
      aria-label={`Contacts and note for ${companyName}`}
      className="grid gap-3 md:grid-cols-2"
    >
      <div className="ht-detail-card ht-company-contacts space-y-3">
        <h3 className="ht-detail-heading">
          <Users aria-hidden className="size-4" />
          Contacts
        </h3>
        {items.length === 0 ? (
          <p className="text-sm">No contacts yet.</p>
        ) : (
          <ul
            aria-label={`Contacts at ${companyName}`}
            className="max-h-72 space-y-2 overflow-y-auto pr-1"
          >
            {items.map((contact) => (
              <ContactItem key={contact.id} contact={contact} companyId={companyId} />
            ))}
          </ul>
        )}
        {adding ? (
          <ContactForm
            initial={EMPTY}
            pending={add.isPending}
            error={add.error}
            onCancel={() => {
              add.reset()
              setAdding(false)
            }}
            onSubmit={(values) => add.mutate(values, { onSuccess: () => setAdding(false) })}
          />
        ) : (
          <Button type="button" size="sm" variant="outline" onClick={() => setAdding(true)}>
            Add a contact
          </Button>
        )}
      </div>
      <div className="ht-detail-card ht-company-note space-y-3">
        <h3 className="ht-detail-heading">
          <StickyNote aria-hidden className="size-4" />
          Note
        </h3>
        <NoteEditor
          key={note?.updated_at ?? 'none'}
          companyId={companyId}
          companyName={companyName}
          initial={note?.body ?? ''}
        />
      </div>
    </section>
  )
}
