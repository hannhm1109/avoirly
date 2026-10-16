# Synthetic pilot policy

Operator decisions recorded **16 October 2026**:

| Topic | Current setting |
| --- | --- |
| Participants | Exactly the existing two synthetic test accounts; no new invitations |
| Public registration | Disabled; the API also checks the two account UUIDs |
| Allowed documents | Synthetic documents only until real-participant admission is explicitly opened |
| Live case retention | Until manually deleted; no automatic 30-day expiry |
| Backup retention | 14 days, with purging dependent on successful jobs |
| Public support/privacy contact | Deferred by the operator; must be supplied before real participants |
| Private alert destination | Configured privately; never displayed as the public contact |

The application, self-hosted Supabase Auth, PostgreSQL and private Storage run
on the Oracle VM in Casablanca, Morocco. Encrypted recovery copies also reside
on the operator's Windows computer outside OneDrive; its physical location is
not independently attested. This is not an exclusively Morocco-resident service.

Automatic extraction sends PO/invoice content to OpenAI. Manual review can
produce a comparison without a model call. Credit evidence is stored privately
and is not sent to the extraction model. Requests disable response storage;
this is not Zero Data Retention. Provider project residency/data controls have
not been independently attested for real documents. Gmail receives the operator
address and static operational alert content, not case files or raw logs.
See [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data).

Deletion revokes active case access immediately and queues durable physical file
cleanup. Quota/technical usage records can remain until administrative purging;
container logs are bounded by size. Retained encrypted backups can contain deleted
cases until they expire. Apply post-snapshot deletions before a restored service
reopens. No automated account erasure or legal-compliance certification is claimed.

The French `/confidentialite` page describes these settings. When the public
contact is ready, set `AVOIRLY_PUBLIC_CONTACT` privately to an email address or
HTTPS contact URL, recreate the web container and verify the page. It is read at
runtime; no image rebuild is required for a contact change. Do not substitute the
private alert address. Confirm participants, document authorization, provider data
controls and appropriate privacy information before admitting real supplier data.
