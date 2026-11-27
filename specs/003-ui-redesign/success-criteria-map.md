# Success criteria map (003-ui-redesign)

| SC | What proves it |
|---|---|
| SC-001 | `frontend/e2e/mobile.spec.ts` (no sideways overflow, lists offending elements; four destinations in the bottom bar); `Shell.test.tsx` |
| SC-002 | `src/theme/contrast.test.ts`; Impeccable `detect` over the running pages (see `verification.md`) |
| SC-003 | `src/theme/stages.test.ts`, `src/theme/tokens.scan.test.ts` |
| SC-004 | `src/theme/tokens.scan.test.ts`, `motion.test.ts`, `surfaces.test.ts`; Hallmark `sloplint` re-run (`verification.md`) |
| SC-005 | Hallmark re-run against `.hallmark/before.txt`; kept findings and reasons in `verification.md` |
| SC-006 | Impeccable critique, recorded in `verification.md` |
| SC-007 | Full Vitest run, and all 11 Playwright journeys (T028) |
| SC-008 | `ProfilePage` / `ProfileSummary` tests; screenshots in `verification.md` |
| SC-009 | Phase checkpoints reviewed by Ravi, one commit per phase |
