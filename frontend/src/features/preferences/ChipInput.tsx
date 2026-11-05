import { X } from 'lucide-react'
import { type KeyboardEvent, useState } from 'react'

const input = 'w-full rounded-md border border-muted-foreground bg-background px-3 py-2 text-sm'

/** A list of short texts: type and press Enter or comma to add; click x to remove. */
export function ChipInput({
  id,
  value,
  onChange,
  placeholder,
}: {
  id: string
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
}) {
  const [draft, setDraft] = useState('')

  function commit() {
    const text = draft.trim()
    setDraft('')
    if (text === '') return
    const key = text.toLocaleLowerCase()
    if (value.some((v) => v.trim().toLocaleLowerCase() === key)) return
    onChange([...value, text])
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault() // Enter must not submit the form
      commit()
    } else if (event.key === 'Backspace' && draft === '' && value.length > 0) {
      onChange(value.slice(0, -1))
    }
  }

  return (
    <div className="space-y-2">
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {value.map((item) => (
            <li
              key={item}
              className="flex items-center gap-1 rounded-full border border-border bg-muted px-3 py-1 text-sm"
            >
              {item}
              <button
                type="button"
                aria-label={`Remove ${item}`}
                className="rounded-full p-0.5 hover:bg-background"
                onClick={() => onChange(value.filter((v) => v !== item))}
              >
                <X className="size-3" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      <input
        id={id}
        className={input}
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={commit}
      />
    </div>
  )
}
