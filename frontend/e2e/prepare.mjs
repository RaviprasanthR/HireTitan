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
const boards = join(root, '.e2e', 'fake_career_ops')
rmSync(boards, { recursive: true, force: true })
cpSync(join(root, 'backend', 'tests', 'fixtures', 'career_ops', 'e2e'), boards, { recursive: true })
console.log(`prepared ${target}, ${seed} and ${boards}`)
