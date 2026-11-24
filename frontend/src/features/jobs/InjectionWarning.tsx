export type InjectionFlag = {
  rule_id: string
  severity: string
  excerpt: string
  location: string
}

/** Shown when a posting contains text that looks like instructions to an AI (FR-038). */
export function InjectionWarning({ flags }: { flags: InjectionFlag[] }) {
  if (flags.length === 0) return null
  // text found in an alert email (feature 002c) is said to come from the email
  const fromEmail = flags.every((flag) => flag.location === 'email')
  return (
    <div role="alert" className="space-y-1 rounded-lg border border-warning p-3 text-sm">
      <p className="font-medium text-warning">
        {fromEmail
          ? 'This email contains text that looks like instructions to an AI. HireTitan ignored it.'
          : 'This posting contains text that looks like instructions to an AI.'}
      </p>
      {!fromEmail && (
        <p>It was treated as plain text and did not change any decision. Be careful with it.</p>
      )}
      <ul className="list-disc pl-5">
        {flags.map((flag) => (
          <li key={`${flag.rule_id}:${flag.excerpt}`}>
            {flag.excerpt
              ? `“${flag.excerpt}” (${flag.location})`
              : `a rule matched (${flag.location})`}
          </li>
        ))}
      </ul>
    </div>
  )
}
