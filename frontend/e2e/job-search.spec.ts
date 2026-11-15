import { execSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { expect, test, type APIRequestContext } from '@playwright/test'

// Quickstart A of feature 002: approve rules, search, jobs appear, skipped list and restore,
// I applied and undo, paste a duplicate, search again. Runs against the compose stack with the
// synthetic company list (.e2e/seed), the fake job boards (.e2e/fake_career_ops) and the
// scripted AI (one judge_relevance reply for the four jobs that pass the rules).

const resume = fileURLToPath(
  new URL('../../backend/tests/fixtures/resumes/synthetic-mid-2page.pdf', import.meta.url),
)
const keyStatusFile = fileURLToPath(new URL('../../.e2e/fake_llm/key_status', import.meta.url))
const restartWorker = () =>
  execSync(
    process.env.E2E_RESTART_WORKER ??
      'docker compose -p hiretitan-e2e -f docker-compose.yml -f docker-compose.e2e.yml restart worker',
    { cwd: fileURLToPath(new URL('../..', import.meta.url)), stdio: 'inherit' },
  )

type Job = { id: string; title: string; company: string; sources: unknown[]; status?: string }
const exploreJobs = async (request: APIRequestContext): Promise<Job[]> =>
  (await (await request.get('/api/v1/jobs?list=explore')).json()).items

test('SC002_job_search_journey', async ({ page, request }) => {
  test.setTimeout(240_000)

  // A clean start: no data (the synthetic company list comes back), key working, reply script
  // from the top.
  writeFileSync(keyStatusFile, 'working\n')
  expect(
    (await request.post('/api/v1/data/delete-all', { data: { confirm: 'DELETE' } })).status(),
  ).toBe(204)
  restartWorker()

  // Setup: name, resume, confirmed profile, one target role.
  await page.goto('/')
  await page.getByLabel('Your name').fill('Jane')
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.locator('input[type="file"]').setInputFiles(resume)
  await expect(page.getByRole('heading', { name: 'Check your profile' })).toBeVisible({
    timeout: 90_000,
  })
  await page.getByRole('button', { name: 'Confirm profile' }).click()
  await page.getByLabel('Target roles').fill('Backend Engineer')
  await page.getByLabel('Target roles').press('Enter')
  await page.getByRole('button', { name: 'Finish setup' }).click()
  await expect(page.getByRole('heading', { name: 'Jobs', level: 1 })).toBeVisible()
  // Home opens on In pipeline (empty at first); the search lives in Explore.
  await expect(page.getByRole('link', { name: 'In pipeline' })).toHaveAttribute('aria-current', 'page')
  await page.getByRole('link', { name: 'Explore' }).click()

  // 1. Explore does not show the setup checklist.
  await expect(page.getByRole('list', { name: 'Setup checklist' })).toHaveCount(0)

  // 2. Search rules (a Profile tab): proposed from the profile, then approved.
  await page.goto('/profile/search-rules')
  await page.getByRole('button', { name: 'Suggest rules' }).click()
  await expect(page.getByRole('region', { name: /job titles/i })).toBeVisible()
  await page.getByRole('button', { name: /approve/i }).click()
  await expect(page.getByText(/rules approved/i)).toBeVisible()

  // 3. Search now: the run finishes and the jobs are listed.
  await page.goto('/explore')
  await page.getByRole('button', { name: 'Search now' }).click()
  await expect(page.getByRole('link', { name: 'See the summary' })).toBeVisible({
    timeout: 120_000,
  })

  // 4. Only the relevant jobs are listed; the rest are on the summary and can be restored.
  await expect.poll(async () => (await exploreJobs(request)).length).toBe(2)
  await page.getByRole('link', { name: 'See the summary' }).click()
  await expect(page.getByRole('button', { name: 'Restore' }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Restore' }).first().click()
  await expect.poll(async () => (await exploreJobs(request)).length).toBe(3)

  // 5. I inquired puts a job In pipeline as Inquired; I applied turns it into Applied; the
  // company shows it. Every mark is one click (SC-002), and Undo is one click too.
  await page.goto('/explore')
  await page.getByRole('button', { name: 'I inquired' }).first().click()
  await expect.poll(async () => (await exploreJobs(request)).length).toBe(2)
  await page.getByRole('link', { name: 'In pipeline' }).click()
  await expect(page.getByText('Inquired', { exact: true }).first()).toBeVisible()
  await page.getByRole('link', { name: 'Explore' }).click()
  await page.getByRole('button', { name: 'Undo' }).click()
  await expect.poll(async () => (await exploreJobs(request)).length).toBe(3)

  await page.getByRole('button', { name: 'I applied' }).first().click()
  await expect.poll(async () => (await exploreJobs(request)).length).toBe(2)
  await page.getByRole('link', { name: 'In pipeline' }).click()
  await expect(page.getByText('Applied', { exact: true }).first()).toBeVisible()
  await page.getByRole('link', { name: 'Companies' }).click()
  await expect(page.getByText('Applied', { exact: true }).first()).toBeVisible()
  await page.getByRole('link', { name: 'Home', exact: true }).click() // the toast stays (Home is In pipeline)
  await page.getByRole('button', { name: 'Undo' }).click()
  await expect.poll(async () => (await exploreJobs(request)).length).toBe(3)

  // 6. Pasting a job whose link is already listed keeps one entry and adds a source.
  const listed = (await exploreJobs(request))[0]
  const detail = await (await request.get(`/api/v1/jobs/${listed.id}`)).json()
  const link: string = detail.sources[0].url
  await page.goto('/explore')
  await page.getByRole('button', { name: 'Add a job' }).click()
  await page.getByLabel('Link to the job').fill(`${link}?utm_source=pasted`)
  await page
    .getByLabel('Job description')
    .fill('The same posting pasted from another site. '.repeat(3))
  await page.getByRole('button', { name: 'Save job' }).click()
  await expect.poll(async () => (await exploreJobs(request)).length).toBe(3)
  const after = await (await request.get(`/api/v1/jobs/${listed.id}`)).json()
  expect(after.sources.length).toBeGreaterThanOrEqual(2)

  // 7. Searching again judges nothing new: the script has no second reply, so any new AI call
  // would fail the run.
  await page.goto('/explore')
  await page.getByRole('button', { name: 'Search now' }).click()
  await expect(page.getByRole('link', { name: 'See the summary' })).toBeVisible({
    timeout: 120_000,
  })
  await expect.poll(async () => (await exploreJobs(request)).length).toBe(3)

  // 7b. Interview tracking (feature 002e): mark a job applied, open its row, record a contact, a
  // hiring firm, two rounds and a question; the Status column follows the latest round.
  await page.goto('/explore')
  await page.getByRole('button', { name: 'I applied' }).first().click()
  await expect.poll(async () => (await exploreJobs(request)).length).toBe(2)
  await page.getByRole('link', { name: 'In pipeline' }).click()
  // the row's details are read-only; the interview records are changed in the edit card
  await page.getByRole('button', { name: /^Edit / }).first().click()
  const card = page.getByRole('dialog', { name: /^Edit / })
  const details = card.getByRole('region', { name: 'Interview details' })
  await expect(details).toBeVisible()

  await details.getByLabel('Contact name').fill('Asha Rao')
  await details.getByRole('button', { name: 'Save contact' }).click()
  await expect(details.getByText('Contact saved.')).toBeVisible()

  await details.getByLabel('Through a hiring firm').check()
  await details.getByLabel('Firm name').fill('TalentBridge')
  await details.getByRole('button', { name: 'Save source' }).click()
  await expect(details.getByText('Source saved.')).toBeVisible()

  await details.getByRole('button', { name: 'Add round' }).click()
  const round1 = details.getByRole('form', { name: 'Round 1', exact: true })
  await round1.getByLabel('Result').selectOption('cleared')
  await round1.getByRole('button', { name: 'Save round 1' }).click()
  await expect(round1.getByText('Round saved.')).toBeVisible()

  await details.getByRole('button', { name: 'Add round' }).click()
  await expect(details.getByRole('form', { name: 'Round 2', exact: true })).toBeVisible()

  const ask = details.getByRole('form', { name: 'Add a question to round 2' })
  await ask.getByLabel('New question').fill('How would you shard a large table?')
  await ask.getByRole('button', { name: 'Add question' }).click()
  await expect(details.getByRole('form', { name: 'Edit question 1', exact: true })).toBeVisible()

  expect(await details.innerText()).not.toMatch(/AI cost|cost so far|budget|\bspend\b|\bspent\b/i)

  await page.keyboard.press('Escape')
  await expect(card).toBeHidden()
  await expect(page.getByText('Round 2 scheduled', { exact: true }).first()).toBeVisible()

  // 8. No page talks about AI cost or a budget (SC-005). "$" is not checked: pay can use it.
  const cost = /AI cost|cost so far|budget|\bspend\b|\bspent\b/i
  for (const path of [
    '/',
    '/explore',
    '/companies',
    '/profile',
    '/profile/preferences',
    '/profile/search-rules',
    '/review',
    '/settings',
    '/search/history',
  ]) {
    await page.goto(path)
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
    expect(await page.locator('main').innerText(), path).not.toMatch(cost)
  }
})
