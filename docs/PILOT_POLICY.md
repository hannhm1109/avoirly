# Synthetic pilot policy

Operator decisions recorded **16 October 2026**:

| Topic                          | Current setting                                                                |
| ------------------------------ | ------------------------------------------------------------------------------ |
| Participants                   | Exactly the existing two synthetic test accounts; no new invitations           |
| Public registration            | Disabled; the API also checks the two account UUIDs                            |
| Allowed documents              | Synthetic documents only until real-participant admission is explicitly opened |
| Live case retention            | Until manually deleted; no automatic 30-day expiry                             |
| Backup retention               | 14 days, with purging dependent on successful jobs                             |
| Public support/privacy contact | avoirly.support@gmail.com, configured and verified on the live privacy page    |
| Operational alert destination  | avoirly.support@gmail.com, selected by the operator for all project contact    |
| Operational alert sender       | avoirly.support@gmail.com; authenticated, with test alert accepted by Gmail    |

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

The French `/confidentialite` page describes these settings and displays the
operator-approved public address **avoirly.support@gmail.com**. The operator also
selected that account for operational alerts. The earlier personal alert address
is not published. Alerts now use the support account as both sender and recipient.
Its dedicated app password was authenticated and installed privately; Gmail
accepted one test alert. No supplier email sending is enabled.

`AVOIRLY_PUBLIC_CONTACT` is read at runtime; recreating the web container applies
a replacement email address or HTTPS contact URL without rebuilding the image.
Confirm participants, document authorization, provider data controls and appropriate
privacy information before admitting real supplier data.
