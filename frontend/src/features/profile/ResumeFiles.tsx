import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertDialog } from 'radix-ui'
import { useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { type ResumeFile, deleteResume, fetchResumes } from './api'

const KIND: Record<string, string> = {
  upload_pdf: 'PDF',
  upload_docx: 'Word',
  pasted_text: 'Pasted text',
}

function sizeLabel(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** The stored resume files, each with a delete action (FR-034). */
export function ResumeFiles() {
  const queryClient = useQueryClient()
  const [target, setTarget] = useState<ResumeFile | null>(null)
  const [error, setError] = useState<string | null>(null)
  const query = useQuery({
    queryKey: ['resumes'],
    queryFn: fetchResumes,
    refetchOnWindowFocus: false,
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteResume(id),
    onSuccess: async () => {
      setTarget(null)
      setError(null)
      await Promise.all(
        [['resumes'], ['profile'], ['onboarding'], ['status'], ['review-items']].map((queryKey) =>
          queryClient.invalidateQueries({ queryKey }),
        ),
      )
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.detail : 'Something went wrong. Please try again.'),
  })

  const files = query.data ?? []
  if (query.isError) return <p role="alert">Could not load your resume files.</p>
  if (files.length === 0) return null

  return (
    <section className="max-w-2xl space-y-3" aria-labelledby="resume-files-heading">
      <h2 id="resume-files-heading" className="text-lg font-medium">
        Your resume files
      </h2>
      <ul className="space-y-2">
        {files.map((f) => (
          <li key={f.id} className="flex flex-wrap items-center gap-3 rounded-lg bg-surface p-3">
            <span className="font-medium">{f.original_name}</span>
            <span className="text-sm text-muted-small">
              {KIND[f.kind] ?? f.kind} · {sizeLabel(f.size_bytes)} ·{' '}
              {new Date(f.created_at).toLocaleDateString('en-GB')}
            </span>
            <Button
              variant="outline"
              className="ml-auto"
              aria-label={`Delete ${f.original_name}`}
              onClick={() => {
                setError(null)
                setTarget(f)
              }}
            >
              Delete
            </Button>
          </li>
        ))}
      </ul>

      <AlertDialog.Root open={target !== null} onOpenChange={(open) => !open && setTarget(null)}>
        <AlertDialog.Portal>
          <AlertDialog.Overlay className="fixed inset-0 bg-black/60" />
          <AlertDialog.Content className="fixed top-1/2 left-1/2 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-lg bg-surface p-6">
            <AlertDialog.Title className="text-lg font-semibold">
              Delete {target?.original_name}?
            </AlertDialog.Title>
            <AlertDialog.Description className="space-y-2 text-sm text-muted-small">
              <span className="block">
                The file is removed from this computer. Any versions you already confirmed keep
                their content and are marked as having no source file.
              </span>
              {target?.has_open_review && (
                <span className="block">
                  This file has an unsaved review. Deleting the file discards that review.
                </span>
              )}
            </AlertDialog.Description>
            {error && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            <div className="flex gap-3">
              <Button
                disabled={remove.isPending}
                onClick={(event) => {
                  event.preventDefault() // stay open until the server answers
                  if (target) remove.mutate(target.id)
                }}
              >
                Delete file
              </Button>
              <AlertDialog.Cancel asChild>
                <Button variant="secondary">Cancel</Button>
              </AlertDialog.Cancel>
            </div>
          </AlertDialog.Content>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </section>
  )
}
