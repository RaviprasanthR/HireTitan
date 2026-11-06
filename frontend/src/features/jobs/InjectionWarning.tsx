export type InjectionFlag = {
  rule_id: string
  severity: string
  excerpt: string
  location: string
}

/** Shown when a posting contains text that looks like instructions to an AI (FR-038). */
export function InjectionWarning({ flags }: { flags: InjectionFlag[] }) {
  if (flags.length === 0) return null
  return (
    <div role="alert" className="space-y-1 rounded-lg border border-warning p-3 text-sm">
      <p className="font-medium text-warning">
        This posting contains text that looks like instructions to an AI.
      </p>
      <p>It was treated as plain text and did not change any decision. Be careful with it.</p>
      <ul className="list-disc pl-5">
        {flags.map((flag) => (
          <li key={`${flag.rule_id}:${flag.excerpt}`}>
            “{flag.excerpt}” ({flag.location})
          </li>
        ))}
      </ul>
    </div>
  )
}
