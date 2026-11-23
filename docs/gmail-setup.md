# Connect Gmail (job alerts)

HireTitan can read the **job-alert emails** that LinkedIn, Naukri, Indeed, foundit, Instahyre and
Cutshort send you, and add those jobs to Explore. This page is the one-time setup.

> **Draft.** Google changes its console now and then, so the menu names below may differ a little.
> The steps will be checked against a real Google account before the feature is released.

## What HireTitan can and cannot do with your mailbox

- It asks Google for **read-only** access (`gmail.readonly`) and nothing wider. If Google ever
  grants more than that, HireTitan refuses it and hands it back at once.
- It only asks Gmail for mail **from the sender addresses on the list in Settings, and from each
  job site's own domain** (for example `naukri.com`), from the **last 24 hours** of each check. Mail
  from a site's domain that holds no job alert is dropped. You can switch any site off, or add your
  own addresses.
- It **never sends, deletes, labels or changes** a message, and it does not keep the emails: only a
  note of which messages it has read, so none is read twice.
- **With an AI key set, the AI reads each alert email** to take out the title, company and place
  of every job, because the sites change their email layouts often. The email's text (cleaned up,
  never your Google sign-in) goes to your AI provider for that. A company or place the AI names
  that is not written in the email is dropped, and the email's footer ("This email was intended
  for ...") is never taken as a value. Without a key, HireTitan's own readers read the emails.
- **Read the last day again** (Settings → Gmail, after the first check) reads the last 24 hours of
  alerts once more, so jobs found earlier get the company and place a better reading finds.
- Your Google client ID, client secret and sign-in token stay in your own data folder
  (`secrets/gmail.json`), on your computer. They are never shown, logged or sent to the AI.
- **Disconnect** in Settings hands the access back to Google and deletes the saved token and the
  notes about read mail. The jobs already found stay.

## Why you create your own Google client

An open-source app cannot ship one shared Google secret for everyone, so each install uses a client
**you** create in your own Google account. It is free, and nothing is published or reviewed by
Google: the client stays in "Testing" mode with you as its only user.

## Steps

1. **Create a project.** Open <https://console.cloud.google.com/>, then *Select a project* →
   *New project*. Name it anything (for example `HireTitan`).
2. **Turn on the Gmail API.** *APIs & Services* → *Library* → search *Gmail API* → *Enable*.
3. **Set up the consent screen.** *APIs & Services* → *OAuth consent screen* (or *Google Auth
   platform* → *Branding*). Choose user type **External**, give the app a name and your email, and
   keep the publishing status on **Testing**.
4. **Add yourself as a test user.** On the same screen, *Audience* (or *Test users*) → *Add users*
   → your own Gmail address. Without this Google refuses the sign-in.
5. **Add the scope** (if Google asks for scopes): `https://www.googleapis.com/auth/gmail.readonly`
   and nothing else.
6. **Create the client.** *APIs & Services* → *Credentials* → *Create credentials* →
   *OAuth client ID* → application type **Web application**.
7. **Register the redirect address.** Under *Authorised redirect URIs* add the address that
   HireTitan shows in **Settings → Gmail job alerts** (by default
   `http://localhost:8000/api/v1/mail/google/callback`). It must match exactly.
8. **Give HireTitan the two values.** In Settings → Gmail job alerts, either press **Load
   client_secret.json** and choose the JSON file you downloaded in step 6 (Google offers a
   *Download JSON* button when the client is created), or paste the **Client ID** and **Client
   secret** by hand. The file is read in your browser and only the two values are used. Press
   **Save**, then **Connect Gmail**. Settings → Gmail job alerts shows the whole set-up as four
   steps (Google client, Connect, Senders, First check), each marked done, next or waiting; the
   first step lists these Google pages with links and a **Copy** button for the redirect address.
9. **Allow access in Google.** Google warns that the app is not verified; that is expected for your
   own client in Testing mode. Choose *Continue*, check that the only permission listed is
   *View your email messages and settings*, and allow it. You land back in HireTitan, which says
   *Connected as your@address*.

You can set the two values as the environment variables `GOOGLE_OAUTH_CLIENT_ID` and
`GOOGLE_OAUTH_CLIENT_SECRET` instead (for example in `.env`); Settings then says they come from the
environment and does not ask for them.

## Good to know

- **Every 7 days in Testing mode.** Google ends the sign-in of an app in Testing mode after 7 days.
  HireTitan then shows *Gmail access has ended. Connect again.* in Settings; press **Reconnect
  Gmail**. Nothing already found is lost.
- **Changed the client?** Use *Change client ID and secret* in Settings, then connect again. A
  sign-in belongs to the client that made it, so HireTitan forgets the old one.
- **A wrong redirect address** shows a Google error page (`redirect_uri_mismatch`): fix the address
  in the Google console so it matches Settings exactly.

## Disconnecting from Google's side

Disconnect in HireTitan is enough. To check or remove it from Google too, open
<https://myaccount.google.com/permissions> (*Sign-in with Google* / *Third-party apps with account
access*) and make sure the app you created is no longer listed, or remove it there.
