// Resets .e2e/fake_llm to the scripted replies before an end-to-end run, with the AI key
// "missing" so the journey starts with the pause. Run from the repository root or frontend/.
import { cpSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')
const target = join(root, '.e2e', 'fake_llm')
rmSync(target, { recursive: true, force: true })
mkdirSync(target, { recursive: true })
cpSync(join(root, 'backend', 'tests', 'fixtures', 'fake_llm', 'e2e'), target, { recursive: true })
writeFileSync(join(target, 'key_status'), 'missing\n')

// The synthetic company list (with the real synonym table) and the fake job boards.
const seed = join(root, '.e2e', 'seed')
rmSync(seed, { recursive: true, force: true })
mkdirSync(seed, { recursive: true })
cpSync(join(root, 'backend', 'tests', 'fixtures', 'companies', 'e2e', 'companies.yaml'), join(seed, 'companies.yaml'))
cpSync(join(root, 'backend', 'seed', 'title_synonyms.yaml'), join(seed, 'title_synonyms.yaml'))
// the reviewed area and technology tables (feature 002i); the app refuses to start without them
cpSync(join(root, 'backend', 'seed', 'work_areas.yaml'), join(seed, 'work_areas.yaml'))
cpSync(join(root, 'backend', 'seed', 'tech_names.yaml'), join(seed, 'tech_names.yaml'))
// the shipped job-alert senders (feature 002c), so the fake mailbox's alerts have a sender to match
cpSync(join(root, 'backend', 'seed', 'mail_senders.yaml'), join(seed, 'mail_senders.yaml'))
const boards = join(root, '.e2e', 'fake_career_ops')
rmSync(boards, { recursive: true, force: true })
cpSync(join(root, 'backend', 'tests', 'fixtures', 'career_ops', 'e2e'), boards, { recursive: true })
// The fake mailbox (feature 002c, HIRETITAN_MAIL=fake): its address, and an empty messages folder
// the Gmail journey fills with synthetic alerts dated just before it runs.
const mailbox = join(root, '.e2e', 'fake_gmail')
rmSync(mailbox, { recursive: true, force: true })
mkdirSync(join(mailbox, 'messages'), { recursive: true })
writeFileSync(join(mailbox, 'profile.json'), JSON.stringify({ address: 'jane@example.invalid' }))
console.log(`prepared ${target}, ${seed}, ${boards} and ${mailbox}`)
