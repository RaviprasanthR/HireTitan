import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router'
import { ApiError, apiFetch } from '@/api/client'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'
import { ProfileFormFields } from './ProfileFormFields'
import {
  type ApiContent,
  type FormValues,
  emptyContent,
  formSchema,
  toApiContent,
  toFormPath,
  toFormValues,
} from './profileForm'

type ProfileOut = components['schemas']['ProfileOut']

function EditorForm({ initial, hasCurrent }: { initial: ApiContent; hasCurrent: boolean }) {
  const navigate = useNavigate()
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: toFormValues(initial),
  })
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function save(values: FormValues) {
    setFormError(null)
    setBusy(true)
    try {
      await apiFetch('/profile/versions', { method: 'POST', json: toApiContent(values) })
      navigate('/profile')
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        for (const err of e.fieldErrors) {
          if (err.field === 'profile') setFormError(err.message)
          else form.setError(toFormPath(err.field) as never, { type: 'server', message: err.message })
        }
        if (!e.fieldErrors.length) setFormError(e.detail)
      } else {
        setFormError(e instanceof ApiError ? e.detail : 'Something went wrong. Please try again.')
      }
      setBusy(false)
    }
  }

  return (
    <form onSubmit={form.handleSubmit(save)} className="max-w-3xl space-y-6" noValidate>
      <div>
        <h1 className="text-2xl font-semibold">
          {hasCurrent ? 'Edit your profile' : 'Fill in your profile'}
        </h1>
        <p className="text-sm text-muted-small">
          {hasCurrent
            ? 'Each save keeps your earlier versions: this saves as a new version.'
            : 'Type your details in by hand. No resume or AI is needed.'}
        </p>
      </div>
      <ProfileFormFields form={form} />
      {formError && (
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          {formError}
        </p>
      )}
      <Button type="submit" disabled={busy}>
        Save profile
      </Button>
    </form>
  )
}

export function ProfileEditor() {
  const query = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiFetch<ProfileOut>('/profile'),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
  if (query.isPending) return <p>Loading your profile…</p>
  if (query.isError) return <p role="alert">Could not load your profile.</p>
  const current = query.data.current
  return <EditorForm initial={current?.content ?? emptyContent} hasCurrent={current !== null} />
}
