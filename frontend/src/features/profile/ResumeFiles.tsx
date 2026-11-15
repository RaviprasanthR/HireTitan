import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertDialog } from 'radix-ui'
import { useState } from 'react'
import { ApiError, apiFetch } from '@/api/client'
import { Button } from '@/components/ui/button'
import { usePipelineResumes } from '@/features/jobs/resume/resumeApi'
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

/** The names were cleared from the jobs, but the file itself could not be removed. */
class PartialRemoval extends Error {}

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

  // how many pipeline jobs use each file (feature 002f), and whether to clear their names too
  const pipeline = usePipelineResumes()
  const [clearNames, setClearNames] = useState(false)
  // Until the count is known the dialog cannot be confirmed: a count taken as 0 would hide the
  // option to clear the names (FR-009).
  const checking = pipeline.isPending || pipeline.isFetching
  const checkFailed = pipeline.isError
  const uses = target
    ? ((pipeline.data?.usage ?? []).find((u) => u.resume_file_id === target.id)?.jobs ?? 0)
    : 0

  const refreshJobs = () =>
    Promise.all(
      [['pipeline-resumes'], ['jobs'], ['job-interview']].map((queryKey) =>
        queryClient.invalidateQueries({ queryKey }),
      ),
    )

  const remove = useMutation({
    mutationFn: async ({ id, clear }: { id: string; clear: boolean }) => {
      // The jobs are cleared first: once the file is gone nothing points at it any more. If this
      // fails the file stays, and the person sees why.
      if (clear) await apiFetch(`/pipeline/resumes/${id}/uses`, { method: 'DELETE' })
      try {
        return await deleteResume(id)
      } catch (e) {
        if (clear) throw new PartialRemoval(e instanceof ApiError ? e.detail : '')
        throw e
      }
    },
    onSuccess: async () => {
      setTarget(null)
      setError(null)
      await Promise.all([
        ...[['resumes'], ['profile'], ['onboarding'], ['status'], ['review-items']].map(
          (queryKey) => queryClient.invalidateQueries({ queryKey }),
        ),
        refreshJobs(),
      ])
    },
    onError: async (e) => {
      if (e instanceof PartialRemoval) {
        setError(
          `The names were cleared from the jobs, but the file could not be removed${
            e.message ? ` (${e.message})` : ''
          }. Try again.`,
        )
        await refreshJobs() // the jobs changed even though the file did not go
      } else {
        setError(e instanceof ApiError ? e.detail : 'Something went wrong. Please try again.')
      }
    },
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
              variant="danger"
              className="ml-auto"
              aria-label={`Delete ${f.original_name}`}
              onClick={() => {
                setError(null)
                setClearNames(false)
                setTarget(f)
                void pipeline.refetch() // a count that is current, not one from earlier
              }}
            >
              Delete
            </Button>
          </li>
        ))}
      </ul>

      <AlertDialog.Root open={target !== null} onOpenChange={(open) => {
          if (!open && !remove.isPending) setTarget(null)
        }}>
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
              {checking && <span className="block">Checking which jobs use this file…</span>}
              {checkFailed && (
                <span className="block">
                  Could not check which jobs use this file.{' '}
                  <button
                    type="button"
                    className="underline"
                    onClick={() => void pipeline.refetch()}
                  >
                    Try again
                  </button>
                </span>
              )}
              {uses > 0 && (
                <span className="block">
                  Used on {uses} {uses === 1 ? 'job' : 'jobs'}. Their name stays on them as a note
                  you can clear.
                </span>
              )}
            </AlertDialog.Description>
            {uses > 0 && (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={clearNames}
                  disabled={remove.isPending}
                  onChange={(event) => setClearNames(event.target.checked)}
                />
                Also clear the name from these jobs
              </label>
            )}
            {error && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            <div className="flex gap-3">
              <Button
                variant="danger"
                disabled={remove.isPending || checking || checkFailed}
                onClick={(event) => {
                  event.preventDefault() // stay open until the server answers
                  if (target) remove.mutate({ id: target.id, clear: uses > 0 && clearNames })
                }}
              >
                Delete file
              </Button>
              <AlertDialog.Cancel asChild>
                <Button variant="cancel" disabled={remove.isPending}>
                  Cancel
                </Button>
              </AlertDialog.Cancel>
            </div>
          </AlertDialog.Content>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </section>
  )
}
