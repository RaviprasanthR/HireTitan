import { execSync } from 'node:child_process'
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { expect, test, type APIRequestContext } from '@playwright/test'

// Feature 002c quickstart: connect Gmail (the scripted Google of HIRETITAN_MAIL=fake), check the
// job-alert mail, see the alert jobs with their site, a posting two alerts mention shown once,
// restore a job the rules left out, disconnect. The mailbox holds synthetic alerts from
// backend/tests/fixtures/mail, re-dated to the last hour so the 24-hour check reads them.

const root = fileURLToPath(new URL('../..', import.meta.url))
const fixtures = `${root}/backend/tests/fixtures/mail/eml`
const messages = `${root}/.e2e/fake_gmail/messages`
const resume = `${root}/backend/tests/fixtures/resumes/synthetic-mid-2page.pdf`
const keyStatusFile = `${root}/.e2e/fake_llm/key_status`
const restartWorker = () =>
  execSync(
    process.env.E2E_RESTART_WORKER ??
      'docker compose -p hiretitan-e2e -f docker-compose.yml -f docker-compose.e2e.yml restart worker',
    { cwd: root, stdio: 'inherit' },
  )

/** Copy fixture alerts into the fake mailbox as new messages, dated an hour ago. The same alert
 *  saved under two ids stands for two emails that mention the same postings. */
function stageMailbox(mail: Record<string, string>) {
  rmSync(messages, { recursive: true, force: true })
  mkdirSync(messages, { recursive: true })
  const date = new Date(Date.now() - 60 * 60 * 1000).toUTCString().replace('GMT', '+0000')
  for (const [id, fixture] of Object.entries(mail)) {
    const text = readFileSync(`${fixtures}/${fixture}`, 'latin1')
      .replace(/^Date: .*$/m, `Date: ${date}`)
      .replace(/^Message-ID: .*$/m, `Message-ID: <${id}@mail.example.invalid>`)
    writeFileSync(`${messages}/${id}.eml`, text, 'latin1')
  }
}

type Source = { kind: string; site?: string | null }
type Job = { id: string; title: string; company_name: string; sources: Source[] }
const exploreJobs = async (request: APIRequestContext): Promise<Job[]> =>
  (await (await request.get('/api/v1/jobs?list=explore')).json()).items
const fromMail = (jobs: Job[]) => jobs.filter((j) => j.sources.some((s) => s.kind === 'email_alert'))

test('SC001_gmail_alerts_journey', async ({ page, request }) => {
  test.setTimeout(240_000)

  // A clean start, and a mailbox with three alerts: LinkedIn twice (the same email under two
  // ids, so every posting in it is mentioned twice) and Naukri once.
  writeFileSync(keyStatusFile, 'working\n')
  expect(
    (await request.post('/api/v1/data/delete-all', { data: { confirm: 'DELETE' } })).status(),
  ).toBe(204)
  restartWorker()
  stageMailbox({ alertA: 'linkedin-02.eml', alertB: 'linkedin-02.eml', alertC: 'naukri-01.eml' })

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

  // 1. Settings > Gmail: the Google client, then Connect (the scripted Google agrees at once).
  await page.goto('/settings/gmail')
  const steps = page.getByRole('list', { name: 'Gmail set-up steps' })
  await expect(steps).toBeVisible()
  await page.getByLabel('Client ID').fill('demo-client.apps.example.invalid')
  await page.getByLabel('Client secret').fill('demo-client-secret-0123456789')
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('button', { name: 'Connect Gmail' }).click()
  await expect(page.getByText('Connected as jane@example.invalid')).toBeVisible()

  // 2. Explore: check the job-alert mail; the check finishes.
  await page.goto('/explore')
  await page.getByRole('button', { name: 'Check job-alert mail' }).click()
  await expect(page.getByText('Mail check finished.')).toBeVisible({ timeout: 120_000 })

  // 3. The alert jobs are listed with their site, and each posting once although two emails
  // mention the LinkedIn ones.
  await expect.poll(async () => fromMail(await exploreJobs(request)).length).toBeGreaterThan(0)
  const listed = fromMail(await exploreJobs(request))
  const keys = listed.map((j) => `${j.title}|${j.company_name}`)
  expect(new Set(keys).size).toBe(keys.length)
  // The AI read each alert first (FR-013b, scripted in fake_llm/e2e/read_job_alert.json): for
  // Bluefin Travel it gives the title "Backend Engineer" (words of the email's line "Senior Backend
  // Engineer"), which wins over the fixed reader's.
  expect(listed.find((j) => j.company_name === 'Bluefin Travel')?.title).toBe('Backend Engineer')
  const table = page.getByRole('table', { name: 'Jobs' })
  await expect(table.getByText(/LinkedIn|Naukri/).first()).toBeVisible()

  // 4. The summary: emails read, and a job the rules left out can be restored.
  const before = (await exploreJobs(request)).length
  await page.getByRole('link', { name: 'See the summary' }).click()
  await page.getByRole('button', { name: 'Show details', exact: true }).click()
  await page.getByText(/^Jobs left out/).click()
  await page.getByRole('button', { name: 'Restore' }).first().click()
  await expect.poll(async () => (await exploreJobs(request)).length).toBe(before + 1)

  // 5. Disconnect: Gmail is no longer connected and the jobs it found stay in Explore.
  await page.goto('/settings/gmail')
  await page.getByRole('button', { name: 'Disconnect', exact: true }).click()
  await page.getByRole('button', { name: 'Disconnect Gmail' }).click()
  await expect(page.getByText('Not connected')).toBeVisible()
  expect((await exploreJobs(request)).length).toBe(before + 1)
})
