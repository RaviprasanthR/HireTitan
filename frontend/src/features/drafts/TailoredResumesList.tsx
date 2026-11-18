import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { docxUrl, pdfUrl, useDeleteTailored, useTailoredList } from './resumeApi'

/** The resumes tailored to jobs, on the Profile page (they are not stored resume files). */
export function TailoredResumesList() {
  const list = useTailoredList()
  const remove = useDeleteTailored()
  const items = list.data ?? []
  return (
    <section aria-label="Tailored resumes" className="space-y-2">
      <h2 className="text-lg font-semibold">Tailored resumes</h2>
      {list.isSuccess && items.length === 0 && (
        <p className="text-sm text-muted-small">
          None yet. Open a job and choose Tailor my resume.
        </p>
      )}
      {items.length > 0 && (
        <ul className="space-y-1 text-sm">
          {items.map((item) => (
            <li key={item.job_id} className="flex flex-wrap items-center gap-3">
              <span>
                {item.job_title}, {item.company}
              </span>
              <span className="text-muted-small">
                {new Date(item.updated_at).toLocaleDateString()}
              </span>
              <Link to={`/jobs/${item.job_id}/resume`} className="text-link underline">
                Open
              </Link>
              <a href={pdfUrl(item.job_id)} download className="text-link underline">
                PDF
              </a>
              <a href={docxUrl(item.job_id)} download className="text-link underline">
                DOCX
              </a>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`Delete tailored resume for ${item.job_title}`}
                onClick={() => {
                  if (window.confirm('Delete this tailored resume?')) remove.mutate(item.job_id)
                }}
              >
                Delete
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
