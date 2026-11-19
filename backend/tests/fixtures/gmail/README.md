# Gmail and Google sign-in answers

**PROVISIONAL.** These files are written by hand from Google's public documentation (OAuth 2.0 for
web server applications, and the Gmail API reference), with synthetic values: no real account,
address, token or message id. Constitution V asks for *recorded* contract fixtures, so task T004
(a throwaway Google account) replaces them with real answers, tokens and addresses swapped for
synthetic ones. Until then the contract tests prove the code against the documented shapes only.

| File | What Google answers |
|---|---|
| `token_exchange.json` | `POST oauth2.googleapis.com/token`, authorization code for tokens |
| `token_refresh.json` | the same endpoint, `grant_type=refresh_token` |
| `token_invalid_grant.json` | the same endpoint, a revoked or expired refresh token (HTTP 400) |
| `revoke_ok.json` | `POST oauth2.googleapis.com/revoke` |
| `profile.json` | `GET gmail.googleapis.com/gmail/v1/users/me/profile` |
| `unauthorized.json` | any Gmail call with an expired access token (HTTP 401) |
