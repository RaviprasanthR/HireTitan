# Synthetic job-alert emails

Everything in this folder is **made up**: the companies, people, addresses (`@example.invalid`),
job ids and links. No real mail is ever committed (constitution VIII).

- `generate.py` writes `eml/*.eml` and `expected.yaml` deterministically. Run it from `backend/`:
  `python tests/fixtures/mail/generate.py`. Change the generator, not the output.
- `eml/` holds 10 alerts for each of six sites (LinkedIn, Naukri, Indeed, foundit, Instahyre,
  Cutshort), 3 digests in a layout no fixed reader knows, and 2 alerts with planted instructions to
  an AI (one visible, one hidden).
- `expected.yaml` lists the jobs each email holds (title, company or null, location or null,
  posting id, link as given). The reader tests and the SC-002 eval compare against it.

The layouts imitate how each site's alert looks, **from general knowledge**, not from real mail.
They are the best guess until the maintainer checks them against real alerts (task T005); the
readers must be re-checked then.
