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
  await expect(page.getByRole('link', { name: 'In pipeline' })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await page.getByRole('link', { name: 'Explore' }).click()

  // 1. Explore does not show the setup checklist.
  await expect(page.getByRole('list', { name: 'Setup checklist' })).toHaveCount(0)

  // 2. Search rules (a Profile tab): approved by HireTitan when setup finished (002i), in plain
  // words, with the person's area and the title words of other areas to leave out.
  await page.goto('/profile/search-rules')
  await expect(page.getByText(/HireTitan set these up from your profile/)).toBeVisible()
  await expect(page.getByRole('region', { name: 'Jobs we keep' })).toBeVisible()
  const leaveOut = page.getByRole('region', { name: 'Jobs we leave out' })
  await expect(leaveOut.getByText('frontend', { exact: true })).toBeVisible()
  await expect(
    page.getByRole('region', { name: 'What helps rank a job' }).getByText('Back end'),
  ).toBeVisible()
  expect(await page.locator('main').innerText()).not.toMatch(
    /Skips jobs|Guides the AI|Similar title/,
  )

  // 3. Search now: the run finishes and the jobs are listed.
  await page.goto('/explore')
  await page.getByRole('button', { name: 'Search now' }).click()
  await expect(page.getByRole('link', { name: 'See the summary' })).toBeVisible({
    timeout: 120_000,
  })
  // the panel never talks about batches or shows "0 of 0" (002i SC-003)
  const panel = page.getByRole('region', { name: 'Search', exact: true })
  expect(await panel.innerText()).not.toMatch(/batch|\b0 of 0\b/i)

  // 4. Only the relevant jobs are listed; the rest are on the summary and can be restored.
  await expect.poll(async () => (await exploreJobs(request)).length).toBe(2)

  // 4a. A row opens in place (002i US5): the posting's own text, read from its link (the listing
  // had none), and the title links to the posting in a new tab.
  const table = page.getByRole('table', { name: 'Jobs' })
  const withReadText = table.getByRole('row').filter({ hasText: 'Senior Backend Engineer' }).first()
  await withReadText
    .getByRole('button', { name: /show details of senior backend engineer/i })
    .click()
  // the opened details are the next row of the table
  await expect(table.getByText(/Mentor engineers and own reliability/)).toBeVisible()
  const titleLink = withReadText.getByRole('link', { name: 'Senior Backend Engineer' })
  await expect(titleLink).toHaveAttribute('target', '_blank')
  await expect(titleLink).toHaveAttribute('href', /alpha\.example\.test\/jobs\/102/)
  await withReadText
    .getByRole('button', { name: /hide details of senior backend engineer/i })
    .click()
  await expect(table.getByText(/Mentor engineers/)).toHaveCount(0)

  // 4b. The Java posting is left out by the rules, with its reason on the summary (002i US6).
  await page.getByRole('link', { name: 'See the summary' }).click()
  await page.getByRole('button', { name: 'Show details', exact: true }).click() // the summary opens on a chart
  await page.getByText(/^Jobs left out/).click() // folded on the summary (2026-11-18)
  await expect(page.getByText('needs Java, which is not in your skills')).toBeVisible()
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
  await page
    .getByRole('button', { name: /^Edit / })
    .first()
    .click()
  const card = page.getByRole('region', { name: /^Edit / })
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

  // 7c. Resume picker (feature 002f): the setup resume is a stored file. Choose it while marking a
  // job applied, see it in the Resume column, change it in the edit card, then remove the file:
  // the name stays as a removed note until it is cleared.
  const stored = await (await request.get('/api/v1/resumes')).json()
  const fileName: string = stored[0].original_name
  await page.goto('/explore')
  // The row has only the two one-click buttons; the resume choice is in the opened row (002k).
  await expect(page.getByRole('combobox', { name: /^Resume used/ })).toHaveCount(0)
  await page
    .getByRole('button', { name: /^Show details of / })
    .first()
    .click()
  const resumeChoice = page.getByRole('combobox', { name: /^Resume used/ }).first()
  await expect(resumeChoice).toBeVisible()
  await resumeChoice.selectOption(stored[0].id)
  await page.locator('section.ht-section-record').getByRole('button', { name: 'I applied' }).click()
  await expect.poll(async () => (await exploreJobs(request)).length).toBe(1)
  await page.getByRole('link', { name: 'In pipeline' }).click()
  const withResume = page.getByRole('row').filter({ hasText: fileName })
  await expect(withResume).toHaveCount(1) // only the job marked with it
  await withResume.getByRole('button', { name: /^Edit / }).click()
  const resumeCard = page.getByRole('region', { name: /^Edit / })
  await resumeCard.getByRole('combobox', { name: 'Resume file' }).selectOption('')
  await resumeCard.getByRole('button', { name: 'Save resume' }).click()
  await expect(resumeCard.getByText('Resume saved.')).toBeVisible()
  await resumeCard.getByRole('combobox', { name: 'Resume file' }).selectOption(stored[0].id)
  await resumeCard.getByRole('button', { name: 'Save resume' }).click()
  await expect(resumeCard.getByText(`${fileName} · added`, { exact: false }).first()).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(resumeCard).toBeHidden()

  await page.goto('/profile')
  await page.getByRole('button', { name: `Delete ${fileName}` }).click()
  const removal = page.getByRole('alertdialog')
  await expect(removal).toContainText('Used on 1 job.')
  await removal.getByRole('button', { name: 'Delete file' }).click()
  await expect(removal).toBeHidden()
  await page.goto('/')
  const removedNote = page.getByRole('row').filter({ hasText: '(removed)' })
  await expect(removedNote).toHaveCount(1)
  await removedNote.getByRole('button', { name: /^Edit / }).click()
  const noteCard = page.getByRole('region', { name: /^Edit / })
  await noteCard.getByRole('button', { name: 'Clear' }).click()
  await expect(noteCard.getByText('(removed)')).toBeHidden()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('row').filter({ hasText: '(removed)' })).toHaveCount(0)

  // 7d. Outreach drafts (feature 002k): a connection request for someone typed in, at most 200
  // characters, to copy. Nothing is sent.
  await page.goto('/explore')
  await page
    .getByRole('button', { name: /^Show details of / })
    .first()
    .click()
  await page.getByRole('button', { name: 'Connection request' }).click()
  await page.getByLabel('Name', { exact: true }).fill('Asha Rao')
  await page.getByLabel('Role', { exact: true }).fill('Talent Partner')
  await page.getByRole('button', { name: 'Write', exact: true }).click()
  const draftBox = page.getByRole('textbox', { name: 'Draft for Asha Rao' })
  await expect(draftBox).toBeVisible()
  await expect(draftBox).toHaveValue(/^Hi Asha,/)
  expect((await draftBox.inputValue()).length).toBeLessThanOrEqual(200)
  await expect(page.getByText(/^\d+ \/ 200$/)).toBeVisible()
  await expect(
    page.getByText('HireTitan never sends this. Copy it and send it yourself.'),
  ).toBeVisible()

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
