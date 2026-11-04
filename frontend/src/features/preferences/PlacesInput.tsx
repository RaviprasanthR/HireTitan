import { X } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { COUNTRIES } from './iso'
import type { Place } from './preferencesForm'

const input = 'rounded-md border border-muted-foreground bg-background px-3 py-2 text-sm'

const describe = (p: Place) => (p.city ? `${p.city}, ${p.country}` : p.country)

/** Places as city + country; the city is optional ("anywhere in Germany"). */
export function PlacesInput({
  label,
  value,
  onChange,
  defaultCountry,
}: {
  label: string
  value: Place[]
  onChange: (next: Place[]) => void
  defaultCountry: string
}) {
  const [city, setCity] = useState('')
  const [country, setCountry] = useState(defaultCountry)

  function add() {
    const next = { city: city.trim(), country }
    setCity('')
    if (value.some((p) => p.city.toLocaleLowerCase() === next.city.toLocaleLowerCase() && p.country === country)) {
      return
    }
    onChange([...value, next])
  }

  return (
    <div className="space-y-2">
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {value.map((p) => (
            <li
              key={describe(p)}
              className="flex items-center gap-1 rounded-full border border-border bg-muted px-3 py-1 text-sm"
            >
              {describe(p)}
              <button
                type="button"
                aria-label={`Remove ${describe(p)}`}
                className="rounded-full p-0.5 hover:bg-background"
                onClick={() => onChange(value.filter((v) => v !== p))}
              >
                <X className="size-3" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap gap-2">
        <input
          aria-label={`${label} city`}
          className={`${input} min-w-40 flex-1`}
          placeholder="City (optional)"
          value={city}
          onChange={(e) => setCity(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add()
            }
          }}
        />
        <select
          aria-label={`${label} country`}
          className={input}
          value={country}
          onChange={(e) => setCountry(e.target.value)}
        >
          {COUNTRIES.map((c) => (
            <option key={c.code} value={c.code}>
              {c.name}
            </option>
          ))}
        </select>
        <Button type="button" variant="outline" onClick={add}>
          Add {label.toLocaleLowerCase()}
        </Button>
      </div>
    </div>
  )
}
