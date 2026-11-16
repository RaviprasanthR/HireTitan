/** Light phrases shown while a search runs. Plain English, nothing about cost or internals. */
export const SEARCH_PHRASES: readonly string[] = [
  'Knocking on career pages…',
  'Reading job boards, one company at a time…',
  'Sorting the good fits from the rest…',
  'Matching roles to your resume…',
  'Skipping the jobs for stacks you do not use…',
  'Looking for roles at your level…',
  'Checking titles against your skills…',
  'Digging up postings you have not seen…',
  'Teaching the filters what you like…',
  'Still reading, good jobs take a moment…',
  'Sniffing out remote roles…',
  'Polishing the shortlist…',
]

/** A phrase other than ``previous``; ``random`` is injectable so the pick can be tested. */
export function nextPhrase(previous: string | null, random: () => number = Math.random): string {
  const pool = SEARCH_PHRASES.filter((phrase) => phrase !== previous)
  return pool[Math.floor(random() * pool.length)] ?? 'Searching…'
}
