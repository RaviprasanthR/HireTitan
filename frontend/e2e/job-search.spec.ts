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

  // 1. The checklist asks for the rules.
  await expect(page.getByRole('link', { name: 'Review your search rules' })).toBeVisible()

  // 2. Search rules: proposed from the profile, then approved.
  await page.getByRole('link', { name: 'Review your search rules' }).click()
  await expect(page).toHaveURL(/\/profile\/search-rules$/)
  await page.getByRole('button', { name: 'Propose rules' }).click()
  await expect(page.getByRole('region', { name: /job titles/i })).toBeVisible()
  await page.getByRole('button', { name: /approve/i }).click()
  await expect(page.getByText(/rules approved/i)).toBeVisible()

  // 3. Search now: the run finishes and the jobs are listed.
  await page.getByRole('link', { name: 'Home', exact: true }).click()
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
  await page.goto('/')
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
  await page.getByRole('link', { name: 'Home', exact: true }).click() // the toast stays
  await page.getByRole('button', { name: 'Undo' }).click()
  await expect.poll(async () => (await exploreJobs(request)).length).toBe(3)

  // 6. Pasting a job whose link is already listed keeps one entry and adds a source.
  const listed = (await exploreJobs(request))[0]
  const detail = await (await request.get(`/api/v1/jobs/${listed.id}`)).json()
  const link: string = detail.sources[0].url
  await page.goto('/')
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
  await page.goto('/')
  await page.getByRole('button', { name: 'Search now' }).click()
  await expect(page.getByRole('link', { name: 'See the summary' })).toBeVisible({
    timeout: 120_000,
  })
  await expect.poll(async () => (await exploreJobs(request)).length).toBe(3)

  // 8. No page talks about AI cost or a budget (SC-005). "$" is not checked: pay can use it.
  const cost = /AI cost|cost so far|budget|\bspend\b|\bspent\b/i
  for (const path of [
    '/',
    '/pipeline',
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
