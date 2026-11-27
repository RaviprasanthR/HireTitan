import { useState } from 'react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import type { DraftKind } from './api'
import { Send } from 'lucide-react'
import { Section } from '@/features/jobs/Section'
import { DraftPanel } from './DraftPanel'

const CHOICES: { kind: DraftKind; label: string }[] = [
  { kind: 'connection_request', label: 'Connection request' },
  { kind: 'referral_message', label: 'Referral message' },
]

/**
 * "Act on this job": drafts for the person to copy and send themselves. HireTitan never sends
 * anything (constitution I). The tailored resume joins this row in a later step.
 */
export function ActOnJob({ jobId, title }: { jobId: string; title: string }) {
  const [open, setOpen] = useState<DraftKind | null>(null)
  return (
    <Section
      title="Act on this job"
      icon={Send}
      hint="Drafts for you to copy and send yourself. HireTitan never sends anything."
      label={`Act on ${title}`}
    >
      <div className="flex flex-wrap gap-2">
        {CHOICES.map((choice) => (
          <Button
            key={choice.kind}
            type="button"
            variant={open === choice.kind ? 'default' : 'outline'}
            size="sm"
            aria-pressed={open === choice.kind}
            onClick={() => setOpen(open === choice.kind ? null : choice.kind)}
          >
            {choice.label}
          </Button>
        ))}
        <Button asChild variant="outline" size="sm">
          <Link to={`/jobs/${jobId}/resume`}>Tailor my resume</Link>
        </Button>
      </div>
      {open && <DraftPanel key={open} jobId={jobId} kind={open} />}
    </Section>
  )
}
