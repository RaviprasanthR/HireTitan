import { execSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'

// One ordered journey through quickstart A (setup cards, key pause and recovery, profile
// review, preferences, re-upload, file deletion, delete-all) against the compose stack with
// HIRETITAN_LLM=fake. The budget step (A12) is covered by the backend tests: the fake
// provider has zero prices, so its calls can never reach a cap.

const resumes = (name: string) =>
  fileURLToPath(new URL(`../../backend/tests/fixtures/resumes/${name}`, import.meta.url))
const keyStatusFile = fileURLToPath(new URL('../../.e2e/fake_llm/key_status', import.meta.url))
const setKey = (state: 'missing' | 'working') => writeFileSync(keyStatusFile, `${state}\n`)

// The key is read when the worker starts (so is the script of AI replies): fixing the key means
// a restart, like quickstart A4.
const restartWorker = () =>
  execSync(
    process.env.E2E_RESTART_WORKER ??
      'docker compose -p hiretitan-e2e -f docker-compose.yml -f docker-compose.e2e.yml restart worker',
    { cwd: fileURLToPath(new URL('../..', import.meta.url)), stdio: 'inherit' },
  )

test('SC001_journey_completes', async ({ page, request }) => {
  // A clean start every time: no data, the key missing, the reply script from the top.
  setKey('missing')
  expect(
    (await request.post('/api/v1/data/delete-all', { data: { confirm: 'DELETE' } })).status(),
  ).toBe(204)
  restartWorker()

  // A1: a fresh install asks for a name and remembers the step.
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Welcome to HireTitan' })).toBeVisible()
  await page.getByLabel('Your name').fill('Jane')
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByRole('heading', { name: 'Hi Jane, add your resume' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Hi Jane, add your resume' })).toBeVisible()

  // A2/A3: without a key the card says so, and an upload waits instead of failing.
  await expect(page.getByText('Reading a resume needs a working AI key')).toBeVisible()
  await page.locator('input[type="file"]').setInputFiles(resumes('synthetic-mid-2page.pdf'))
  await expect(page.getByText('No AI key is set. Add OPENAI_API_KEY')).toBeVisible()

  // A4 (SC006): fixing the key lets the paused extraction carry on by itself.
  setKey('working')
  restartWorker()
  await expect(page.getByRole('heading', { name: 'Check your profile' })).toBeVisible({
    timeout: 90_000,
  })

  // A5: the extracted details are there; confirm them.
  await expect(page.getByLabel('Employer 1')).toHaveValue('Acme Corp')
  await page.getByRole('button', { name: 'Confirm profile' }).click()

  // A6/A8: preferences, then the finished app opens on the jobs page (feature 002 replaced
  // the home greeting).
  await expect(page.getByRole('heading', { name: 'What are you looking for?' })).toBeVisible()
  await page.getByLabel('Target roles').fill('Backend Engineer')
  await page.getByLabel('Target roles').press('Enter')
  await page.getByRole('button', { name: 'Finish setup' }).click()
  await expect(page.getByRole('heading', { name: 'Jobs', level: 1 })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Preferences' })).toBeVisible()

  // A9/A10: a newer resume opens a review with its changes.
  await page.goto('/profile')
  await page.locator('input[type="file"]').setInputFiles(resumes('synthetic-mid-2page-v2.docx'))
  await page.getByRole('link', { name: 'Review your profile' }).click()
  await expect(page.getByLabel('Job title 1')).toHaveValue('Staff Software Engineer')

  // US4-AS1: deleting that file removes its open review.
  await page.goto('/profile')
  await page.getByRole('button', { name: 'Delete synthetic-mid-2page-v2.docx' }).click()
  await page.getByRole('button', { name: 'Delete file' }).click()
  await expect(page.getByText('synthetic-mid-2page-v2.docx')).toHaveCount(0)
  const files = await (await request.get('/api/v1/resumes')).json()
  expect(files.map((f: { original_name: string }) => f.original_name)).toEqual([
    'synthetic-mid-2page.pdf',
  ])

  // A13 (SC008): delete everything, typed confirmation, back to the first card.
  await page.goto('/settings')
  await page.getByRole('button', { name: 'Delete all my data' }).click()
  const confirm = page.getByRole('button', { name: 'Delete everything' })
  await expect(confirm).toBeDisabled()
  await page.getByLabel(/type DELETE/).fill('DELETE')
  await confirm.click()
  await expect(page.getByRole('heading', { name: 'Welcome to HireTitan' })).toBeVisible()
  const onboarding = await (await request.get('/api/v1/onboarding')).json()
  expect(onboarding.step).toBe(1)
  expect((await (await request.get('/api/v1/resumes')).json()).length).toBe(0)
})
