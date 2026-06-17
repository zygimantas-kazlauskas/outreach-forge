# Sending safety model

Block 6 gives Outreach Forge the ability to send real email through
[Resend](https://resend.com). The design center of the block is the opposite
of "make sending work": it is **make an accidental real send impossible**.
Generating drafts and sending them are fully decoupled, and a real send is
gated behind several independent layers that must *all* pass at the same time.

Everything here is implemented in [`backend/send.py`](../backend/send.py) and
exposed through `POST /emails/{id}/send`. The whole model is testable without
Resend credentials — the single network seam (`send._post_resend`) is mocked
in the test suite, so dry-run and every refusal are proven to never touch the
wire (`backend/tests/test_send.py`).

## The layers (all required for a real send)

A send proceeds only if every check below passes. The first failure raises
`SendRefused`, which the API maps to an HTTP status with the failing layer
named; nothing is written to the provider.

1. **`SEND_MODE`** — the master switch. Unset, `dry_run`, or *any* value other
   than the exact (case-insensitive) string `live` means **no network call ever
   happens**: the would-be send is logged and the row is marked
   `send_status='dry_run'` with a fake `dry-run-…` provider id. Typos and
   unknown values fail safe to dry_run. This is the default, so a fresh
   checkout cannot send.
2. **No auto-send.** Sends happen only through an explicit per-email API call.
   The orchestrator never imports `send.py` — generation and sending stay
   decoupled, so running a batch never mails anyone.
3. **Suppression list** (`unsubscribes` table). Any address on it is refused
   **in every mode, dry_run included** — an unsubscribed address can never be a
   send target, even hypothetically.
4. **`RECIPIENT_ALLOWLIST`** (comma-separated). When set, a live send to any
   address not on the list is refused. Keep it pinned to your own addresses
   while testing deliverability.
5. **`SEND_DAILY_LIMIT`** (default 20). Once today's count of *real* sends (UTC
   calendar day, counted from the DB by `sent_at`, which only real sends
   populate) reaches the cap, further live sends are refused. This enforces
   warmup discipline structurally. It is not atomic — two perfectly
   simultaneous requests could overshoot by one; the cap is a discipline, not a
   security boundary.

Two more guards short-circuit before the layers above: a missing email is a
404, and an already-sent email (status `sent`/`delivered`) is a 409 so a retry
can't double-send. Live mode additionally requires `RESEND_API_KEY` and
`SEND_FROM` to be set, or it refuses with a 503 rather than attempting a send.

Every attempt — refused, dry_run, or sent — is appended to
`backend/logs/send_log.jsonl` (gitignored) as an audit trail.

## Unsubscribe handling

- Every outbound body gets a plain-text opt-out footer appended at send time;
  the stored draft stays clean. The footer currently asks the recipient to
  reply to opt out — a real one-click unsubscribe link needs the deployed URL
  from Block 7.
- `POST /unsubscribes` adds an address manually (idempotent).
- A `complained` webhook event auto-adds the address to the suppression list
  (`source='complaint'`), so a spam complaint permanently stops future sends.

## Webhooks (`POST /webhooks/resend`)

Resend signs webhooks with the Svix scheme. The endpoint verifies the
signature against `RESEND_WEBHOOK_SECRET` before applying anything, and **fails
closed**: if the secret is unset it returns 503, and an unverifiable signature
returns 400. Verified events update the email row:

| Event              | Effect                                            |
| ------------------ | ------------------------------------------------- |
| `email.delivered`  | `send_status = 'delivered'`                       |
| `email.opened`     | `opened_at` set                                   |
| `email.bounced`    | `send_status = 'bounced'`                         |
| `email.complained` | address auto-added to `unsubscribes` (complaint)  |

Events are matched to rows by `provider_message_id`. Verification is
implemented directly over stdlib `hmac` (a few lines) rather than pulling in
the `svix` package; the algorithm is stable and is tested with synthetic
payloads, so no real Resend traffic is needed.

## Going live (when you are ready)

Sending stays in dry_run until you deliberately do all of this in
`backend/.env` (never committed; see `backend/.env.example` for the documented
keys):

1. Verify a sender domain in Resend and set `SEND_FROM` to a verified identity.
2. Set `RESEND_API_KEY`.
3. Set `RECIPIENT_ALLOWLIST` to your own address(es) first and send test mail to
   yourself before mailing anyone real.
4. Set a conservative `SEND_DAILY_LIMIT` and raise it slowly as the domain warms.
5. Configure the Resend webhook to point at `/webhooks/resend` and set
   `RESEND_WEBHOOK_SECRET`.
6. Only then set `SEND_MODE=live`.

Because the layers are independent, forgetting any one of them fails safe
rather than sending something you did not intend.
