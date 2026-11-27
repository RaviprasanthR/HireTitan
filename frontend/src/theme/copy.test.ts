import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = resolve(process.cwd(), 'src')
const read = (path: string) => readFileSync(join(root, path), 'utf8')
const files = (dir: string): string[] =>
  readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return files(path)
    // schema.d.ts is generated from the server's API
    return /\.tsx?$/.test(path) && !/\.(test|d)\./.test(path) ? [path] : []
  })

describe('copy', () => {
  it('test_FR021_no_check_again_label', () => {
    // the AI key button says "Test key", the fit check says "Re-check fit" (FR-021)
    for (const path of files(root)) {
      expect(readFileSync(path, 'utf8'), path).not.toMatch(/check again/i)
    }
  })

  it('test_FR029_honest_copy_unchanged', () => {
    const lines: Record<string, string[]> = {
      'features/drafts/ActOnJob.tsx': ['HireTitan never sends anything.'],
      'features/drafts/DraftPanel.tsx': [
        'HireTitan never sends this. Copy it and send it yourself.',
      ],
      'features/drafts/TailoredResumePage.tsx': ['HireTitan never sends your resume anywhere.'],
      'features/settings/SettingsPage.tsx': [
        'Everything here stays on this computer. Nothing is sent anywhere except to the AI',
      ],
      'features/jobs/InjectionWarning.tsx': [
        'This posting contains text that looks like instructions to an AI.',
        'It was treated as plain text and did not change any decision. Be careful with it.',
      ],
    }
    for (const [path, expected] of Object.entries(lines)) {
      for (const line of expected) expect(read(path), path).toContain(line)
    }
  })
})
