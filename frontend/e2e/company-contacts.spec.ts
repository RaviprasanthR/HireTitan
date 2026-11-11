import { execSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'

// Quickstart of feature 002b: import a company sheet, see the contact counts, reach a company's
// contacts in two clicks or fewer (SC-004), add a contact, export with and without contacts, and
// check that Delete all my data leaves none behind (SC-007). Runs against the compose stack with
// the synthetic company list (.e2e/seed: Example Alpha, Gamma and Delta) and the sample sheet.

const resume = fileURLToPath(
  new URL('../../backend/tests/fixtures/resumes/synthetic-mid-2page.pdf', import.meta.url),
)
const sheet = fileURLToPath(
  new URL('../../backend/tests/fixtures/sheets/product_companies_sample.csv', import.meta.url),
)
const keyStatusFile = fileURLToPath(new URL('../../.e2e/fake_llm/key_status', import.meta.url))
const restartWorker = () =>
  execSync(
    process.env.E2E_RESTART_WORKER ??
      'docker compose -p hiretitan-e2e -f docker-compose.yml -f docker-compose.e2e.yml restart worker',
    { cwd: fileURLToPath(new URL('../..', import.meta.url)), stdio: 'inherit' },
  )

type Company = { name: string; contact_count: number; has_note: boolean }

test('SC004_SC007_company_contacts_journey', async ({ page, request }) => {
  test.setTimeout(240_000)

  // A clean start, then the shortest setup that opens the app.
  writeFileSync(keyStatusFile, 'working\n')
  expect(
    (await request.post('/api/v1/data/delete-all', { data: { confirm: 'DELETE' } })).status(),
  ).toBe(204)
  restartWorker()
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

  // 1. The Companies page lists the synthetic companies, none with contacts yet.
  await page.getByRole('link', { name: 'Companies' }).click()
  const alpha = page.getByRole('listitem', { name: 'Example Alpha' })
  await expect(alpha).toBeVisible()
  await expect(alpha).toContainText('0 contacts')

  // 2. Import the sample sheet: preview first, nothing saved until Confirm.
  await page.getByRole('button', { name: 'Import / export' }).click()
  await page.getByRole('button', { name: 'Import a company sheet' }).click()
  await page.getByLabel('Company sheet (CSV)').setInputFiles(sheet)
  const preview = page.getByRole('region', { name: 'Sheet preview' })
  await expect(preview).toBeVisible()
  await expect(alpha).toContainText('0 contacts') // still nothing saved
  await preview.getByRole('button', { name: 'Confirm import' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'contacts added' })).toBeVisible()

  // 3. The counts show on the rows, and a company added by the sheet is in the list.
  await expect(alpha).toContainText('3 contacts')
  await expect(page.getByRole('listitem', { name: 'Sample Epsilon' })).toBeVisible()

  // 4. SC-004: one click from the Companies page to a company's contacts.
  await page.getByRole('button', { name: 'Details for Example Alpha' }).click()
  const people = page.getByRole('list', { name: 'Contacts at Example Alpha' })
  await expect(people).toContainText('Jane Example')
  await expect(people).toContainText('Recruiter')

  // 5. Add a contact by hand.
  await alpha.getByRole('button', { name: 'Add a contact' }).click()
  await alpha.getByLabel('Name').fill('Test Person')
  await alpha.getByLabel('Role').fill('Hiring Manager')
  await alpha.getByRole('button', { name: 'Save contact' }).click()
  await expect(people).toContainText('Test Person')
  await expect(alpha).toContainText('4 contacts')

  // 6. Export: the plain export has no contacts; the opt-in export has them.
  const link = page.getByRole('link', { name: 'Export CSV' })
  await expect(link).not.toHaveAttribute('href', /include_contacts/)
  await page.getByLabel('Include contacts and notes').check()
  await expect(link).toHaveAttribute('href', /include_contacts=true/)
  const [download] = await Promise.all([page.waitForEvent('download'), link.click()])
  const exported = readFileSync(await download.path(), 'utf-8')
  expect(exported).toContain('Jane Example')
  expect(exported).toContain('Test Person')
  const plain = await request.get('/api/v1/companies/export')
  expect(await plain.text()).not.toContain('Jane Example')

  // 7. SC-007: Delete all my data leaves no contact, no note and no sheet company behind.
  expect(
    (await request.post('/api/v1/data/delete-all', { data: { confirm: 'DELETE' } })).status(),
  ).toBe(204)
  const after: Company[] = (await (await request.get('/api/v1/companies')).json()).items
  expect(after.map((c) => c.name).sort()).toEqual([
    'Example Alpha',
    'Example Delta',
    'Example Gamma',
  ])
  expect(after.every((c) => c.contact_count === 0 && !c.has_note)).toBe(true)
})
