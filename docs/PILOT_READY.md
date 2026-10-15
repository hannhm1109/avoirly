# Finish the deployed private pilot

Avoirly is deployed on the Oracle server. This page separates missing credentials
from acceptance work; it does not certify readiness for real supplier data.

## Configuration status — 15 October 2026

| Setting | Status | Where it belongs |
| --- | --- | --- |
| Supabase publishable/secret keys and JWT signing keys | Configured | Private server runtime; only the publishable key reaches the web service |
| Database password, SSH key, metrics token and backup encryption key | Configured | Protected operator/server storage, outside Git |
| OpenAI project API key | Configured and live-tested | Worker environment only |
| Compatible model and current input/output rates | `gpt-5.4-mini-2026-03-17`; USD 0.75 input / 4.50 output per million tokens | Explicit API/worker model; rates on worker |
| API testing budget and enforced provider spend limit | US$5 initial tests authorized; user confirmed enforced US$5 monthly project limit | Dedicated OpenAI project's Limits settings |
| Alert SMTP app password | Deferred by user; still missing | Protected operations configuration only |
| Alert destination and test authorization | Destination and one Gmail SMTP test authorized | Private operations configuration |

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

The OpenAI secret is already saved and installed. When ready to configure the
remaining Gmail credential, run this from the project folder; input is hidden:

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
- All worker preflight and monitor gates pass; the SMTP hook is installed but
  has no credentials or delivered test. No email has been sent.
- Refreshed encrypted configuration/Auth and application backups copied off the
  VM after configuration, with matching ciphertext checksums.

## Remaining acceptance work

1. Configure operational alerts when the deferred app password is supplied, then
   deliver the already-authorized single test and confirm
   receipt. Verify both monitor and backup failures reach the operator.
2. Establish recurring off-VM application and configuration/Auth backups and
   test full Supabase recovery. The initial encrypted configuration bundle was
   authenticated but has not undergone full provider restoration.
3. Confirm the intended operator contact, participants, data locations and
   retention before real supplier files; update the displayed privacy information.

The [configuration checklist](CONFIGURE.md) remains the acceptance record.
READMEs must distinguish implemented features, actual hosted verification and
pending live gates. New features or paid plans do not replace these checks.
