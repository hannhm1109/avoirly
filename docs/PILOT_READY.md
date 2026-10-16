# Finish the deployed private pilot

Avoirly is deployed on the Oracle server. This page separates missing credentials
from acceptance work; it does not certify readiness for real supplier data.

## Configuration status — checked 16 October 2026

| Setting                                                             | Status                                                                            | Where it belongs                                                         |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Supabase publishable/secret keys and JWT signing keys               | Configured                                                                        | Private server runtime; only the publishable key reaches the web service |
| Database password, SSH key, metrics token and backup encryption key | Configured                                                                        | Protected operator/server storage, outside Git                           |
| OpenAI project API key                                              | Configured and live-tested                                                        | Worker environment only                                                  |
| Compatible model and current input/output rates                     | `gpt-5.4-mini-2026-03-17`; USD 0.75 input / 4.50 output per million tokens        | Explicit API/worker model; rates on worker                               |
| API testing budget and enforced provider spend limit                | US$5 initial tests authorized; user confirmed enforced US$5 monthly project limit | Dedicated OpenAI project's Limits settings                               |
| Alert SMTP app password                                             | Existing transport verified; new support-account sender awaits its app password   | Root-owned mode-0600 operations configuration                            |
| Alert destination and test authorization                            | avoirly.support@gmail.com; prior failure drills completed                         | Private operations configuration                                         |
| Full recovery/off-VM copies                                         | Encrypted full snapshot restored successfully from Windows ciphertext             | Private server exports and LOCALAPPDATA, outside Git/OneDrive            |
| Pilot accounts/retention                                            | Two synthetic accounts only; cases until manual deletion; backups 14 days         | Allowlist and documented pilot policy                                    |
| Public support/privacy contact                                      | avoirly.support@gmail.com configured and verified; real participants still closed | Optional web runtime `AVOIRLY_PUBLIC_CONTACT`                            |

No Stripe key or Supabase Pro subscription is required for Phases 1–5. Billing
and subscriptions are Phase 6. HTTPS certificates are already managed by Caddy;
there is no certificate key to buy or paste into the repository.

The dedicated Avoirly key is configured. For a replacement/new project, set the
approved monthly spend limit and turn on **Enforce a hard limit** in that project's
Limits settings. The app's reported-cost monitor is an estimate, not a provider
billing cap. Initial calls used synthetic documents only. Approximately USD 0.44
in reported test estimates was recorded; provider invoices and remaining credit
were not audited. See [the evaluation](EVALUATION.md),
[OpenAI spend limits](https://developers.openai.com/api/docs/guides/spend-limits)
and [API key security](https://developers.openai.com/api/docs/guides/production-best-practices).

For Gmail SMTP alerts, use a dedicated app password with 2-Step Verification
enabled, never the main Google password. Some accounts cannot create app
passwords; if unavailable, choose another authenticated alert provider. See
[Google's app-password instructions](https://support.google.com/accounts/answer/185833).
No supplier email sending is introduced by operational alerts.

## Enter secrets privately on this Windows computer

OpenAI remains configured. The support/privacy contact and alert recipient are
now **avoirly.support@gmail.com**. To send alerts from that new Gmail account,
create its own dedicated app password with 2-Step Verification enabled and save
it through this hidden prompt from the project folder. The previous account's
app password does not authenticate the new account:

```powershell
.\scripts\save-pilot-secret.ps1 -Name GmailSMTP
```

The helper saves only Windows-user-encrypted files in the ignored `.local/`
directory. It makes no network call and does not alter the server. Tell Codex
which secret is saved. For an API-key rotation, use the same helper with `-Name OpenAI`.
Never paste the secrets into chat. These files cannot be decrypted under another
Windows identity; maintain independent copies in a password manager.

## Verified on the hosted deployment — 14–15 October 2026

- HTTPS, real two-account browser login/reload/logout and secure uncached sessions.
- Owner isolation for case lists, reads, mutations and private file downloads.
- Missing, expired, tampered, wrong-issuer/audience, anonymous and uninvited tokens
  rejected by the deployed API; the invited signed control token succeeded.
  Negative tokens were generated privately for an operator test, not third-party accounts.
- A complete **manual** Chromium workflow with unique synthetic references:
  real PDF/image upload, manual source review, 200.00 MAD potential net credit,
  draft editing/save/reload/copy/download, promise and evidence-backed partial
  credits, audited correction and deletion. No extraction call or email was made.
- A queued manual comparison persisted while the worker was stopped, and
  completed after restarting it. This is not an expired-lease or provider-failure drill.
- Private source/proof uploads and downloads; deletion outbox and monitor healthy.
- Scheduled encrypted backup and independent empty-database restores, with
  encrypted off-VM copies; details and limits in [SELF_HOSTING.md](SELF_HOSTING.md).
- A separate complete hosted **live** Chromium flow on release `5b0941f`: unique
  PDF/image upload, real model extraction, source review, 200.00 MAD draft,
  edit/save/reload/copy/export and mobile layout. Its synthetic case was deleted.
- Expired-lease recovery and controlled provider-connection failure/retry, with
  new successful attempts, isolated test cases and the normal worker restored.
- [Labeled evaluation](EVALUATION.md): 20 development pairs and five fresh held-out
  pairs, zero false drafts, all nine ambiguous cases blocked, one conservative
  supported scan requiring review. This is not a production accuracy guarantee.
- All worker preflight and monitor gates pass. SMTP credentials are installed
  privately and one authorized test alert was accepted by Gmail SMTP. The operator
  confirmed receipt. No supplier email has been sent.
- Refreshed encrypted configuration/Auth and application backups copied off the
  VM after configuration, with matching ciphertext checksums. A further refreshed
  bundle includes SMTP configuration and installed operations units; encryption
  authentication and the off-VM ciphertext checksum passed.

## Operations acceptance — 16 October 2026

Actual monitor and backup failures each triggered a received email. Both services
returned to normal successfully. A full snapshot restored the entire PostgreSQL
cluster, custom configuration/pgsodium key, Auth, Storage and application
configuration from the Windows ciphertext copy, using the separately saved key.
Both account logins, owner isolation, three source/proof hashes, the known
200.00 MAD draft, 100.00 MAD promise, 75.25 MAD evidenced credit and secure web
login/gateway/logout passed. The isolated stack had zero host ports and no
outbound access; it was removed after verification.

The daily full-backup timer and current-user Windows copy task automate recurring
copies. The latter depends on the PC being on, signed in and connected. Full
snapshot/copy freshness checks alert at 30/36 hours respectively. Backup retention
is 14 days, purged after successful jobs. See [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md).

The user selected exactly the existing two synthetic accounts and manual case
deletion. The public privacy page describes these choices, Oracle Casablanca,
Windows recovery copies and external provider limitations. The operator then
provided avoirly.support@gmail.com for both public contact and operational alerts;
the public page and alert recipient have been updated. The earlier personal
address remains unpublished. Sender rotation awaits the new app password.

## Before real participants

The support/privacy contact is now configured and verified. Confirm the
participants' document authorization, provider data controls and applicable
privacy information at that point. No new invitations or real supplier files
are authorized now. A replacement-VM/DNS cutover has not been tested; this remains
an explicitly scoped synthetic demonstration, not a production availability SLA.

The [configuration checklist](CONFIGURE.md) remains the acceptance record.
READMEs must distinguish implemented features, actual hosted verification and
pending live gates. New features or paid plans do not replace these checks.

The initial 16 October documentation check passed all ten worker preflight and
six application monitor checks. Later recovery work added two host freshness
checks and the failure-email drills described above.
