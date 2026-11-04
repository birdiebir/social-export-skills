# Privacy rules for export pipelines

Added 2026-10-01. A personal export contains **other people's** private messages, phone numbers and addresses, sometimes credentials too. The pipeline creates many copies of that data: L1 files, notes, reading dumps, test fixtures, rendered pages. Each copy is another place where it can leak.

## Where data may live

- Raw exports, L1 data, notes and the rendered package stay on the local machine. Don't put them in cloud-synced folders, including an "archive" folder that happens to sync, and don't paste them into online tools.
- Progress dashboards that sync to a public repo or a phone: numbers and status only. No names, addresses or account hints.
- Credentials found in the data (for example a password someone sent in a chat): tell the user so they can change it. Don't copy the credential into notes or reports.

## Masking rendered pages

- **Mask first, then truncate and escape.** If you truncate a snippet first, a phone number or address can be cut in half, the regex no longer matches the visible fragment, and part of it leaks.
- Agree the masking scope with the user and record it as a decision:
  - Which pages? For example, only the risk-review pages, with data files and chat pages unchanged.
  - Which types? For example, mobile numbers and landlines for each relevant country, addresses in each relevant language, map links. Ask about borderline types such as messaging-app IDs.
  - The user's own data or third parties' data? A common answer: mask the user's own phone, but leave the user's own home address visible.
- Exemptions are personal data, so keep them out of the code and out of git:
  - Put the list in `private/<name>.yaml`, which is gitignored.
  - Commit a template in `private.example/`.
  - Store only the path in config.
  - If the file is missing, mask everything. That's the safe default.
- Ask before you exempt anything. An address in the user's own post may belong to someone else (they posted it for a friend), and then it stays masked.
- Unit tests should cover three things: an exempted entry stays visible, a non-exempted address is masked, phones are always masked.

## Test fixtures never use real data

- Use obviously fictional values, for example `100 Example Road, Sampletown`, `0900-000-000`, `Alex Example`.
- Incident: an agent writing tests for a masking function took a real address from the data as its test string. It was committed. A follow-up commit replaced it, but removing it from history meant a rewrite of history.
- Put "test fixtures use fictional data only" into every dispatch prompt for agents that may write tests, and check new test files before committing.

## Temporary working files

- Reading dumps, excerpt files and before-snapshots for regression diffs all contain private messages.
- Keep them in a gitignored `tmp/` folder. List them in the agent's report, and delete them once the batch passes verification. Don't leave them for "later cleanup" without a checklist item.

## Scan the notes themselves for PII (added 2026-10)

- AI-written notes can copy a third party's phone number, email or address straight from a private message into the narrative or a quote. In one project a note contained a third party's mobile number, and it was only noticed by chance during an unrelated quote review. Masking rendered pages doesn't help here, because the notes are an asset of their own.
- Do: run a PII scan over all notes (template: `scripts/pii_scan_template.py`) and wire it into the project's verify step:
  - Start as **WARN**, with output limited to file, line and kind (never the matched text).
  - Upgrade to **FAIL** once the keep rules are agreed.
- Use the same patterns as the page masking, so the two can't drift apart.
- **Keep rules** need a written reason, for example:
  - risk-review records that must keep the original text as a cleanup anchor (masked only when displayed);
  - an exclusion list whose keys are group names that contain an ad phone number.
- How masking works:
  - Outside quotes, replace the item with a placeholder such as "(phone omitted)".
  - Inside a verbatim quote, replace only the PII with "…", so the rest still passes strict verification.
  - If a quote is nothing but PII, drop the whole quote.
  - Mask the superseded copies in the same folder as well.
  - Afterwards, spot-check that IDs weren't mistaken for phone numbers (this happened, and the IDs had to be restored).
- The user's own email or phone: mask by default. Only an explicit exemption in `private/` keeps them.
- If PII already reached git history, rewriting history needs the user's own approval (see `parallel-agents.md` on the auto-mode classifier).
- **Fixtures, again:** test strings for PII scanners must be fully fictional, down to the street name. A real street name in a test is still a real address hint.
