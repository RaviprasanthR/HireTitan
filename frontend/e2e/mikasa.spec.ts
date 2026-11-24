import { execSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

// Feature 002m journey (scripted AI): open Mikasa, quick actions run with no typing, add a
// job from a link and mark it applied in one message, Undo it (the link can be added again), add it
// again, delete it through a confirm card, and an off-topic request is refused. The AI replies come
// from .e2e/fake_llm (mikasa_topic.json and mikasa_turn.turns.json).

const root = fileURLToPath(new URL('../..', import.meta.url))
const resume = `${root}/backend/tests/fixtures/resumes/synthetic-mid-2page.pdf`
const keyStatusFile = `${root}/.e2e/fake_llm/key_status`
const turnsFile = `${root}/.e2e/fake_llm/mikasa_turn.turns.json`
const initialTurns = JSON.parse(
  readFileSync(`${root}/backend/tests/fixtures/fake_llm/e2e/mikasa_turn.turns.json`, 'utf8'),
) as unknown[]
const restart = (service: string) =>
  execSync(
    process.env[`E2E_RESTART_${service.toUpperCase()}`] ??
      `docker compose -p hiretitan-e2e -f docker-compose.yml -f docker-compose.e2e.yml restart ${service}`,
    { cwd: root, stdio: 'inherit' },
  )

type Job = { id: string; title: string; state: string }
const jobs = async (request: APIRequestContext, list: string): Promise<Job[]> =>
  (await (await request.get(`/api/v1/jobs?list=${list}`)).json()).items

async function ask(page: Page, text: string) {
  const box = page.getByLabel('Message to Mikasa')
  await box.fill(text)
  await box.press('Enter')
}

test('SC001_mikasa_journey', async ({ page, request }) => {
  test.setTimeout(240_000)

  // A clean start: the AI key works, the scripted turns start from the top, the app is empty.
  writeFileSync(keyStatusFile, 'working\n')
  writeFileSync(turnsFile, JSON.stringify(initialTurns))
  restart('api') // the fake AI keeps its place in the script in memory
  await expect
    .poll(
      async () => {
        try {
          return (await request.get('/api/v1/health')).ok() // it throws while the API restarts
        } catch {
          return false
        }
      },
      { timeout: 60_000 },
    )
    .toBe(true)
  expect(
    (await request.post('/api/v1/data/delete-all', { data: { confirm: 'DELETE' } })).status(),
  ).toBe(204)

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

  // 1. Open Mikasa: quick actions first, no text box until asked for.
  await page.getByRole('button', { name: 'Mikasa' }).click()
  const panel = page.getByRole('complementary', { name: 'Mikasa' })
  await expect(panel).toBeVisible()
  await expect(page.getByRole('main')).toBeVisible() // the page stays beside her
  await expect(panel.getByLabel('Message to Mikasa')).toHaveCount(0)

  // 2. Quick actions run at once (no AI call): add a job with the form, then mark it applied.
  await panel.getByRole('button', { name: 'Add a job' }).click()
  const paste = panel.getByRole('form', { name: 'Paste a job description' })
  await paste.getByLabel('Link to the job').fill('https://jobs.example.com/acme/e2e-0')
  await paste.getByLabel('Job title (optional)').fill('Platform Engineer')
  await paste.getByLabel('Company (optional)').fill('Acme')
  await paste
    .getByLabel('Job description')
    .fill('We build the platform that runs our payment services. You will own it end to end.')
  await paste.getByRole('button', { name: 'Save job' }).click()
  await expect(panel.getByText('Added Platform Engineer at Acme.')).toBeVisible({ timeout: 30_000 })

  await panel.getByRole('button', { name: "Update a job's status" }).click()
  const status = panel.getByRole('form', { name: "Update a job's status" })
  await status.getByLabel('Job').selectOption({ label: 'Platform Engineer at Acme' })
  await status.getByLabel('Status').selectOption('applied')
  await status.getByRole('button', { name: 'Update' }).click()
  await expect.poll(async () => (await jobs(request, 'pipeline')).length).toBe(1)
  // ... and take it back, so the rest of the journey starts from an empty pipeline
  await panel.getByRole('button', { name: "Update a job's status" }).click()
  const again = panel.getByRole('form', { name: "Update a job's status" })
  await again.getByLabel('Job').selectOption({ label: 'Platform Engineer at Acme' })
  await again.getByLabel('Status').selectOption('not_applied')
  await again.getByRole('button', { name: 'Update' }).click()
  await expect.poll(async () => (await jobs(request, 'pipeline')).length).toBe(0)

  // 3. Ask something else: add a job from its link and mark it applied, in one message.
  await panel.getByRole('button', { name: 'Ask something else' }).click()
  const message = 'I applied to https://jobs.example.com/acme/e2e-1, Backend Engineer at Acme'
  await ask(page, message)
  const notice = panel.getByRole('status').filter({ hasText: 'marked it applied' })
  await expect(notice).toBeVisible({ timeout: 30_000 })
  await expect.poll(async () => (await jobs(request, 'pipeline')).length).toBe(1)

  // 4. Undo removes it, and the same link can be added again.
  await notice.getByRole('button', { name: 'Undo' }).click()
  await expect(panel.getByText('Undone.')).toBeVisible()
  await expect.poll(async () => (await jobs(request, 'pipeline')).length).toBe(0)
  await ask(page, message)
  await expect(
    panel.getByRole('status').filter({ hasText: 'marked it applied' }).last(),
  ).toBeVisible({
    timeout: 30_000,
  })
  await expect.poll(async () => (await jobs(request, 'pipeline')).length).toBe(1)
  const [job] = await jobs(request, 'pipeline')
  if (!job) throw new Error('the job was not added again')

  // 5. A risky change waits for confirmation: nothing is deleted until Confirm.
  const known = JSON.parse(readFileSync(turnsFile, 'utf8')) as unknown[]
  writeFileSync(
    turnsFile,
    JSON.stringify([
      ...known,
      [{ tool_call: { id: 'd1', name: 'delete_job', arguments: { job: `job:${job.id}` } } }],
      [{ text: 'I prepared the deletion. Confirm it below.' }],
    ]),
  )
  await ask(page, 'Delete that job')
  await expect(panel.getByText('Delete: Backend Engineer at Acme')).toBeVisible({ timeout: 30_000 })
  expect((await request.get(`/api/v1/jobs/${job.id}`)).status()).toBe(200) // still there
  await panel.getByRole('button', { name: 'Confirm' }).click()
  await expect(panel.getByText('Done.').last()).toBeVisible()
  await expect.poll(async () => (await request.get(`/api/v1/jobs/${job.id}`)).status()).toBe(404)

  // 6. Anything off topic is refused, with the quick actions still there.
  await ask(page, 'Write me a poem about autumn')
  await expect(panel.getByText(/I can only help with your own job search/).last()).toBeVisible({
    timeout: 30_000,
  })
  await expect(panel.getByRole('button', { name: 'LinkedIn connection message' })).toBeVisible()

  // 7. The post-to-draft flow: pick a draft, paste a post, get the draft, then say yes to saving.
  await panel.getByRole('button', { name: 'LinkedIn connection message' }).click()
  await panel
    .getByLabel('Job post or link')
    .fill(
      'Platform Engineer at Initech. We build the platform that runs our payment services, in Python and PostgreSQL. You will own it end to end with a small team. https://jobs.example.com/initech/platform-1',
    )
  await panel.getByRole('button', { name: 'Continue' }).click()
  await expect(panel.getByText('Would you like me to save')).toBeVisible({ timeout: 60_000 })
  // nothing is saved yet: the post is not in Explore
  const before = await request.get('/api/v1/jobs?list=explore')
  expect(JSON.stringify(await before.json())).not.toContain('Initech')
  await panel.getByRole('button', { name: 'Yes, save it' }).click()
  await expect
    .poll(async () => JSON.stringify(await (await request.get('/api/v1/jobs?list=explore')).json()))
    .toContain('Initech')
})
