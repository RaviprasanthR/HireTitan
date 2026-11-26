import { execSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { expect, test, type Page } from '@playwright/test'

// Feature 003 US1: every part of the app on a phone (FR-014 to FR-018, SC-001). Runs against the
// compose e2e stack; a clean start and the shortest setup come first.

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

const ROUTES = ['/', '/explore', '/companies', '/profile', '/settings']

// No sideways scroll, and nothing cut off at the right edge either: overflow-x is clipped on the
// root, so scrollWidth alone would hide an element that runs off the screen. The visually hidden
// table heads are skipped. A string: the e2e project has no DOM types.
const overflowing = async (page: Page) =>
  (await page.evaluate(`[
    ...(document.documentElement.scrollWidth > window.innerWidth ? ['html'] : []),
    ...[...document.body.querySelectorAll('*')]
      .filter((el) => !el.closest('thead') && el.getBoundingClientRect().right > window.innerWidth + 1)
      .map((el) => el.tagName + '.' + String(el.className).slice(0, 60)),
  ]`)) as string[]

test.describe.serial('mobile', () => {
  test.beforeAll(async ({ browser, request }) => {
    test.setTimeout(240_000)
    writeFileSync(keyStatusFile, 'working\n')
    expect(
      (await request.post('/api/v1/data/delete-all', { data: { confirm: 'DELETE' } })).status(),
    ).toBe(204)
    restartWorker()
    const page = await browser.newPage()
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
    await page.close()
  })

  test('US1_AS1_bottom_bar_on_phone', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/')
    const nav = page.getByRole('navigation', { name: 'Main' })
    await expect(nav.getByRole('link')).toHaveCount(4)
    const box = await nav.boundingBox()
    expect(box && Math.round(box.y + box.height)).toBe(844)
    // each item shows its name, not just an icon
    for (const link of await nav.getByRole('link').all()) {
      await expect(link).toHaveText(/\w+/)
      const b = await link.boundingBox()
      expect(b?.height ?? 0).toBeGreaterThanOrEqual(44)
    }
  })

  test('US1_AS2_settings_reachable_on_phone', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/')
    await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'Settings' })
      .click()
    await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible()
  })

  for (const width of [390, 320]) {
    test(`SC001_no_sideways_scroll_on_any_page_${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 640 })
      for (const route of ROUTES) {
        await page.goto(route)
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
        expect(await overflowing(page), route).toEqual([])
      }
    })
  }

  test('EC_landscape_phone_content_not_hidden', async ({ page }) => {
    await page.setViewportSize({ width: 844, height: 390 })
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Jobs', level: 1 })).toBeInViewport()
    expect(await overflowing(page)).toEqual([])
  })

  test('EC_zoom_200_no_clipping', async ({ page }) => {
    // 1280 CSS px at 200% zoom lays out like a 640px-wide window
    await page.setViewportSize({ width: 640, height: 400 })
    for (const route of ROUTES) {
      await page.goto(route)
      expect(await overflowing(page), route).toEqual([])
    }
    const nav = page.getByRole('navigation', { name: 'Main' })
    for (const name of ['Companies', 'Profile', 'Settings']) {
      await expect(nav.getByRole('link', { name })).toBeVisible()
    }
  })
})
