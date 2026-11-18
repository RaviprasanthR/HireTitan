import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { useJob } from '@/features/explore/api'
import { AddDescriptionDialog } from '@/features/jobs/AddDescriptionDialog'
import { LeaveGuard } from '@/features/jobs/interview/LeaveGuard'
import { InjectionNotice } from './DraftPanel'
import {
  MISSING_TEXT,
  type ResumeDoc,
  type Tailored,
  docxUrl,
  pdfUrl,
  useDeleteTailored,
  useSaveTailored,
  useStartTailor,
  useTailored,
} from './resumeApi'

const input = 'w-full rounded-md border border-muted-foreground bg-background px-3 py-1.5 text-sm'

function KeywordMatch({ match }: { match: NonNullable<Tailored['keyword_match']> }) {
  return (
    <section aria-label="Keyword match" className="space-y-1 rounded-lg bg-surface p-3 text-sm">
      <p className="font-medium">Keyword match: {Math.round(match.score * 100)}%</p>
      {match.matched.length > 0 && <p>In this resume: {match.matched.join(', ')}</p>}
      {match.missing.length > 0 && (
        <ul className="list-disc pl-5">
          {match.missing.map((m) => (
            <li key={m.keyword}>
              {m.keyword}: {MISSING_TEXT[m.reason]}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Editor({ jobId, tailored }: { jobId: string; tailored: Tailored }) {
  const saved = tailored.document as ResumeDoc
  const [doc, setDoc] = useState<ResumeDoc>(saved)
  // the saved version this editor last took; a newer one replaces the form only if untouched
  const [seen, setSeen] = useState<ResumeDoc>(saved)
  if (JSON.stringify(saved) !== JSON.stringify(seen)) {
    if (JSON.stringify(doc) === JSON.stringify(seen)) setDoc(saved)
    setSeen(saved)
  }
  const save = useSaveTailored(jobId)
  const start = useStartTailor(jobId)
  const remove = useDeleteTailored()
  const navigate = useNavigate()
  const dirty = JSON.stringify(doc) !== JSON.stringify(saved)
  const experience = doc.experience ?? []

  function setBullet(job: number, index: number, text: string) {
    setDoc({
      ...doc,
      experience: experience.map((e, i) =>
        i === job
          ? {
              ...e,
              bullets: (e.bullets ?? []).map((b, j) => (j === index ? text : b)),
            }
          : e,
      ),
    })
  }

  function again() {
    if ((dirty || tailored.edited) && !window.confirm('Your edits will be replaced. Tailor again?'))
      return
    start.mutate(true)
  }

  function del() {
    if (!window.confirm('Delete this tailored resume?')) return
    remove.mutate(jobId, { onSuccess: () => void navigate(`/jobs/${jobId}`) })
  }

  return (
    <div className="space-y-4">
      <LeaveGuard when={dirty} />
      {tailored.source === 'fallback' && (
        <p className="text-sm text-muted-small">
          The AI’s rewording was not used, so this is your profile in its own wording, ordered for
          this job.
        </p>
      )}
      {tailored.keyword_match && <KeywordMatch match={tailored.keyword_match} />}

      <article
        aria-label="Resume preview"
        className="space-y-4 rounded-lg border border-divider p-4"
      >
        <header>
          <h2 className="text-xl font-semibold">{doc.contact.name}</h2>
          <p className="text-sm text-muted-small">
            {[doc.contact.email, doc.contact.phone, doc.contact.location]
              .filter(Boolean)
              .join(' | ')}{' '}
            <Link to="/profile/edit" className="text-link underline">
              Edit contact details in your profile
            </Link>
          </p>
        </header>
        <label className="block space-y-1 text-sm">
          <span className="font-medium">Summary</span>
          <textarea
            className={input}
            rows={4}
            value={doc.summary ?? ''}
            maxLength={1200}
            onChange={(event) => setDoc({ ...doc, summary: event.target.value })}
          />
        </label>
        <section className="space-y-3">
          <h3 className="font-medium">Experience</h3>
          {experience.map((job, jobIndex) => (
            <div key={job.id} className="space-y-1">
              <p className="text-sm font-medium">
                {job.title}, {job.employer}
                <span className="text-muted-small">
                  {' '}
                  {[job.dates, job.location].filter(Boolean).join(' | ')}
                </span>
              </p>
              {(job.bullets ?? []).map((bullet, bulletIndex) => (
                <div key={bulletIndex} className="flex gap-2">
                  <textarea
                    aria-label={`${job.employer} bullet ${bulletIndex + 1}`}
                    className={input}
                    rows={2}
                    maxLength={400}
                    value={bullet}
                    onChange={(event) => setBullet(jobIndex, bulletIndex, event.target.value)}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={`Remove ${job.employer} bullet ${bulletIndex + 1}`}
                    onClick={() =>
                      setDoc({
                        ...doc,
                        experience: experience.map((e, i) =>
                          i === jobIndex
                            ? {
                                ...e,
                                bullets: (e.bullets ?? []).filter((_, j) => j !== bulletIndex),
                              }
                            : e,
                        ),
                      })
                    }
                  >
                    ✕
                  </Button>
                </div>
              ))}
            </div>
          ))}
        </section>
        <label className="block space-y-1 text-sm">
          <span className="font-medium">Skills (comma separated)</span>
          <input
            className={input}
            value={(doc.skills ?? []).join(', ')}
            onChange={(event) =>
              setDoc({
                ...doc,
                skills: event.target.value
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
          />
        </label>
        {(doc.projects ?? []).length > 0 && (
          <section className="space-y-1 text-sm">
            <h3 className="font-medium">Projects</h3>
            {(doc.projects ?? []).map((p) => (
              <p key={p.id}>{p.name}</p>
            ))}
          </section>
        )}
        {(doc.education ?? []).length > 0 && (
          <section className="space-y-1 text-sm">
            <h3 className="font-medium">Education</h3>
            {(doc.education ?? []).map((e) => (
              <p key={e.id}>
                {e.institution} {[e.detail, e.dates].filter(Boolean).join(' | ')}
              </p>
            ))}
          </section>
        )}
        {(doc.certifications ?? []).length > 0 && (
          <section className="space-y-1 text-sm">
            <h3 className="font-medium">Certifications</h3>
            {(doc.certifications ?? []).map((c) => (
              <p key={c.id}>{c.issuer ? `${c.name} (${c.issuer})` : c.name}</p>
            ))}
          </section>
        )}
      </article>

      {(save.isError || start.isError) && (
        <p role="alert" className="text-sm text-danger">
          {(save.error ?? start.error)?.message}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate(doc)}
        >
          Save
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={start.isPending || save.isPending}
          onClick={again}
        >
          Tailor again
        </Button>
        <Button asChild variant="outline" size="sm">
          <a href={pdfUrl(jobId)} download>
            Download PDF
          </a>
        </Button>
        <Button asChild variant="outline" size="sm">
          <a href={docxUrl(jobId)} download>
            Download DOCX
          </a>
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={del}>
          Delete
        </Button>
      </div>
      <p className="text-xs text-muted-small">
        Download saves the last saved version. HireTitan never sends your resume anywhere.
      </p>
    </div>
  )
}

/** The resume tailored to one job: tailor it, edit it, see the keyword match, download it. */
export function TailoredResumePage() {
  const { id = '' } = useParams()
  const job = useJob(id)
  const tailored = useTailored(id)
  const start = useStartTailor(id)
  const started = useRef(false)
  const [needsText, setNeedsText] = useState(false)
  const missing = tailored.isSuccess && tailored.data === null

  const { mutate } = start
  const begin = useCallback(
    (regenerate: boolean) =>
      mutate(regenerate, {
        onError: (error) => {
          started.current = false // a failed start can be tried again
          if (error instanceof ApiError && error.problem.reason === 'no_description') {
            setNeedsText(true)
          }
        },
      }),
    [mutate],
  )

  useEffect(() => {
    if (!missing || started.current) return
    started.current = true
    begin(false)
  }, [missing, begin])

  const data = tailored.data
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">
        Tailored resume
        {job.data ? `: ${job.data.title}, ${job.data.company_name}` : ''}
      </h1>
      <p>
        <Link to={`/jobs/${id}`} className="text-link underline">
          Back to the job
        </Link>
      </p>
      <InjectionNotice signals={data?.injection_signals} />
      {needsText && (
        <AddDescriptionDialog
          jobId={id}
          onCancel={() => setNeedsText(false)}
          onSaved={() => {
            setNeedsText(false)
            begin(false)
          }}
        />
      )}
      {tailored.isError && <p role="alert">Could not load the tailored resume.</p>}
      {start.isError && !needsText && (
        <div className="space-y-2">
          <p role="alert" className="text-danger">
            {start.error.message}
          </p>
          {missing && (
            <Button type="button" variant="outline" size="sm" onClick={() => begin(false)}>
              Try again
            </Button>
          )}
        </div>
      )}
      {data?.status === 'writing' && (
        <div className="space-y-1">
          <p role="status">Tailoring…</p>
          {data.paused_reason && <p className="text-sm text-danger">{data.paused_reason}</p>}
        </div>
      )}
      {data?.status === 'failed' && (
        <div className="space-y-2">
          <p role="alert" className="text-danger">
            {data.failure_reason ?? 'The resume could not be tailored.'}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={start.isPending}
            onClick={() => begin(true)}
          >
            Tailor again
          </Button>
        </div>
      )}
      {data?.status === 'ready' && data.document && <Editor key={id} jobId={id} tailored={data} />}
    </section>
  )
}
