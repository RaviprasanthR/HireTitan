# Quickstart: Gmail job alerts (002c)

How to see the feature work. Details are in [spec.md](spec.md), [data-model.md](data-model.md) and [contracts/rest-api.md](contracts/rest-api.md).

## 1. Automated checks (no Google account needed)

From `backend/`:

```bash
uv run pytest tests/unit/mail tests/contract/gmail tests/integration/mail tests/api/mail tests/workflow/mail -q
uv run pytest tests/architecture -q        # no-send scan covers hiretitan.mail; allowlist; import contracts
uv run python -m evals.run mail_alerts     # SC-002 on the synthetic alerts, readers only, no AI, no key
```

Expected: all pass; the eval report shows ≥ 95% of jobs read correctly, 0 invented values, ≥ 90% of built-in emails read without AI.

From `frontend/`: `npm test`, `npm run build`, then the Playwright journey (§4).

## 2. Connect a real Gmail account (SC-001, timed)

Use a Google account you are happy to test with.

1. In Google Cloud Console create a project, enable the **Gmail API**, configure the OAuth consent screen as **External** in **Testing**, add your own address under **Test users**.
2. Create an **OAuth client ID** of type **Web application**; add the redirect URI shown in HireTitan's Settings (`http://localhost:8000/api/v1/mail/google/callback` by default).
3. In HireTitan → Settings → Gmail: paste the client id and secret, press **Connect**, approve in Google's window.

Expected: Settings shows "Connected as <address>"; Google's consent screen listed only "Read your email messages and settings" (read-only); `<data_dir>/secrets/gmail.json` exists and its contents appear in no log. Time from step 1 to connected: under 15 minutes.

## 3. Read a day of alerts

1. Make sure job-alert emails arrived in the last 24 hours from a built-in sender (or add your own sender in Settings → Gmail → Senders).
2. On Explore press **Check job-alert mail**.

Expected:
- The search panel shows the check's progress, then its summary; Search history lists it.
- New jobs appear in Explore with "Email alert · <site>" and the alert date; source filter **Email alerts** shows only them.
- Jobs left out by your rules are on the summary page with their reason and **Restore**.
- Press the button again: "No new job-alert emails since <time>"; nothing is added (each email is read once).
- A job you already had from a company search shows the alert as another source, not a second row.

Optional, counts only: `uv run python scripts/check_my_alerts.py` prints, per sender and reader, how many emails and jobs the readers found in your last 24 hours. Never commit its output.

## 4. Playwright (scripted Gmail, no account)

The e2e stack sets `HIRETITAN_MAIL=fake` with `.e2e/fake_gmail/` holding synthetic Gmail API answers. The journey: connect (the fake consent returns at once), check mail, see alert jobs in Explore with their site, a repeated job once, a left-out job restored from the summary, disconnect.

## 5. Disconnect and delete

- Settings → Gmail → **Disconnect**: Settings shows "Not connected"; your Google account's **Third-party access** page no longer lists the app (SC-006); jobs from alerts stay.
- Settings → **Delete all my data**: the Gmail connection, secrets file, senders and read-email records are gone.

## 6. Failure paths to try

- Revoke the app in your Google account, then check mail: "Gmail access has ended. Reconnect to keep reading job alerts."
- Remove your AI key and add a sender whose emails no reader knows: those emails count as "could not read" and are read on a later check once the key is back (inside 24 hours).
