import { formatDay } from '@/features/explore/api'
import type { ResumeFile } from '@/features/profile/api'

/**
 * "Resume used": the person's stored resume files by name and the day each was added, then
 * None (an empty value). It shows nothing when there is no file to choose from.
 */
export function ResumeSelect({
  files,
  value,
  onChange,
  disabled,
  id,
  label = 'Resume used',
}: {
  files: ResumeFile[]
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  id?: string
  /** The name of the choice; the mark control and the edit card are on one page and differ. */
  label?: string
}) {
  if (files.length === 0) return null
  return (
    <label className="flex flex-col gap-1 text-sm">
      {label}
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="max-w-64 rounded-md border border-muted-foreground bg-background px-3 py-1.5 text-sm"
      >
        <option value="">None</option>
        {files.map((file) => (
          <option key={file.id} value={file.id}>
            {file.original_name} · added {formatDay(file.created_at.slice(0, 10))}
          </option>
        ))}
      </select>
    </label>
  )
}
