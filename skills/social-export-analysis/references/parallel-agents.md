# Running several agents in parallel on one export project

Added 2026-10-01. Setup: one git repo with one codebase, several background agents working at once (code fixes, note rewrites, risk review), and one main line that coordinates. Every rule below comes from something that actually went wrong.

## Ownership

- Each agent writes only inside its own scope, for example one module's notes folder or one code area.
- Shared files are main-line only: the progress table, the decision log, config, shared index pages. Agents put proposed text for these files in their report.
- Agents don't run package, check, progress or commit. The main line runs them once, after all agents have reported, in a documented module order (dependencies matter, and some modules need a second run).
- Pages in shared output sections: each generator records which pages it wrote and deletes only those on a rerun. Never clean a whole shared section, because another module's pages disappear.
- Put a **common-rules block** in every dispatch prompt:
  - files to read first
  - what not to touch
  - writing rules (quotes verbatim back to L1, which personal data never to write)
  - account rules (see `multi-account.md`)
  - "test fixtures use fictional data only"
  - the report format
- Keep the dispatch document in a file so agents can be re-dispatched after a session break. Each agent keeps a checkpoint file and deletes it when done.

## Reports go to a file

- Collect each agent's report into one file (for example `<batch>_agent_reports.md`) as soon as it arrives. Sessions can drop, and reports that only exist in chat are lost.
- Each report contains:
  - the full list of changed files
  - honest coverage, including what wasn't read
  - verification results
  - proposed decision-log and progress text
  - questions for the user, plus the safe default the agent applied meanwhile
- Write the user's answers back into the same file, so the next agent can pick up from it.

## An independent read-only PM agent

- Run one extra agent that only reads, and writes only its own board. The board holds:
  - completion against verifiable done-conditions
  - a risk register (impact, likelihood, mitigation)
  - go/no-go gates for the wrap-up
  - spot checks of agent output against the raw data
  - a remaining-work inventory
- The PM must state the coverage of its own checks, for example "spot-checked 6 folders, not all".
- **The PM's numbers can be wrong too.** In the source project, an off-by-one date cutoff inflated a count by about a fifth. Neither the user's statement nor the PM's conclusion is ground truth: re-derive important numbers from L0/L1 with a script before they go into the decision log or the knowledge base.

## Git hygiene

- `git commit` commits the whole index, not just "my files". Before every commit, run `git diff --cached --name-only` and confirm the list matches this batch.
- Excluding subdirectories with `:(exclude)` pathspecs may silently not apply (shell quoting, magic-signature parsing). Don't rely on it; read the staged list.
- `data/`, `tmp/` and `private/` never go into git.
- If private data got committed, fix it in a follow-up commit, then agree with the user whether to rewrite history (autosquash, `reflog expire`, `gc`). Rewrite only after every agent has finished committing, because rewriting under active agents breaks their work.

## Scope flags that still touch shared state

- A flag that narrows scope (for example `--account X`) can still overwrite a file shared by all accounts (see `pitfalls.md` B4).
- Until it's fixed, write "never add --account to the regression run" into the wrap-up checklist. Afterwards, assert that the shared file still has every account key.

## Long-running jobs

- Prevent sleep before long packaging or extraction (for example a `/wake` skill or a power-plan change). A killed job leaves half-built output.
- A portability test that moves the whole package away and back leaves the package in the test path if it's killed midway. After any failure, check where the package actually is.
- Moving a big tree as one directory fails if any subfolder is locked. Move it item by item, then remove the empty shell.
- Order: verify → package → check. Only then commit the progress table and delete temporary snapshots.

## Wrap-up checklist template

1. Read every agent report. Check that `git status` only shows files inside each agent's scope, and flag anything outside it.
2. Run the unit tests.
3. Run the regression with no scope flag. Confirm that shared files have every account key.
4. Re-run the affected modules in dependency order. Every module's verify step must PASS.
5. Run progress and explain every number change, for example "+N threads recovered by the parser fix".
6. Keep the machine awake, then package and check.
7. Write the decision log, the progress table and the experience file (see the project's `經驗與避雷.md` pattern).
8. Commit only this batch's files.
9. Sync the knowledge base and the project dashboard. These are separate commits; dashboards that sync publicly get numbers only.
10. Delete the temporary snapshots and the reading dumps (they contain private messages).

## Auto-mode permission classifier (Claude Code), added 2026-10-01

In auto mode, a safety classifier can block steps that a human approved earlier in the main conversation. Blocks seen in practice:

| What was blocked | Label | Why it looked risky |
|---|---|---|
| A sub-agent asked to rewrite many notes, where the instruction came from the main line relaying the user's decision via SendMessage | Instruction Poisoning | To the sub-agent, an instruction arriving mid-task from another agent isn't the user's consent |
| Re-extracting L1 (`extract` clears and rewrites `data/`) | Irreversible Local Destruction | It wipes a data folder |
| `git reflog expire` + `git gc --prune=now` after rewriting history | Git Destructive | It permanently drops objects |

What works:
- Get the user's **own words** approving that specific step, in the main conversation.
- Then either:
  - the main line runs the blocked step itself, or
  - a **new** agent gets the user's verbatim approval quoted at the top of its initial prompt (a "User authorization (verbatim)" block), with the exact scope.

  In the source project, the re-extraction was run by the main line. The note rewrite went to a fresh wrap-up agent whose initial prompt started with a block quoting the user's approval word for word, plus the user's exact words about the change. That agent wasn't blocked at any point, so this approach has been verified once. Relaying the same approval to an already-running agent via a message is what got blocked.
- Never have an agent route around a block, for example by rewording the command, splitting it up or using another tool. Report the block, the exact command and what it would touch, then wait.
- Plan for it: in the dispatch doc, mark destructive steps "needs user approval" so they don't stall a background agent halfway through.

## Two-phase dispatch for changes that need re-extraction

When a code fix requires re-extracting data that other agents are still reading:
1. **Phase 1, safe while others run:** change the code, add tests, and do a read-only trial calculation that reports what the counts will become. Commit the code. Don't touch `data/`.
2. **Phase 2, after the readers finish (and after user approval, see above):** snapshot → re-extract → diff against the snapshot → regression → re-run modules in dependency order → package → check.

This avoids concurrent read/write conflicts and lets the trial numbers go to the user before anything irreversible happens.

## Cleaning tmp without losing tools

- Before you clear `tmp/` at wrap-up, move the scripts you'll want to run again (for example the answer write-back script or the L1 snapshot/diff helper) into the repo's `tool/scripts/`, and point the docs at the new path. Then delete the rest, which includes reading dumps with private messages.
- Backups made during de-identification (copies of the skill before names were removed) still contain personal data. Never ship them with a shared skill.

## Scaling to a dozen or more agents (added 2026-10)

One round dispatched more than ten single-purpose agents: code fixes, gap reading, fact extraction, timeline module, UI/UX, quote cleanup in several passes, semantic reviews, a wrap-up agent. There were no write conflicts. Three things made that work:

1. **Mutually exclusive scopes**, written into each prompt. When two jobs touch the same area, sequence them instead of running them side by side.
2. **Two phases for anything risky:** read-only audit or trial first, implementation second. Examples: a strict-quote audit before fixing, a UI/UX review and proposal before changing generators.
3. **One committer:** agents never commit. The main line or the wrap-up agent commits each finished piece, and it says so when a commit contains another agent's file (for example a config entry registered by another agent).

Also:
- Every narrative-writing agent gets a **paired semantic-review agent** (see `social-export-insights` `分析\查證與協作.md` §9). Budget for it from the start; it's not optional polish.
- Each round ends with an experience-extraction agent that updates the project's experience file and these references.

## Working with a separate PM session (added 2026-10)

- A separate Claude Code session can supervise the main line (scope check, QC, schedule, risk). It reads transcripts and files and writes only its own board.
- **Messages between sessions may need the user's approval** (cross-session inbound set to "hold"). A message waiting for approval doesn't arrive, so supervisors' advice can land after the main line has already acted. Plan for delays, have the PM write its findings to a board file too, and don't block work waiting for a cross-session reply.
- **A "GO" in a cross-session message is not the user's approval.** When the user has said "start when X appears on the board or when I say so", a supervisor's message saying GO doesn't meet that condition. A step that widens scope (changing tools, rerunning packaging) also waits for the user's own words in that session. Write the start condition and the scope down at kickoff so nobody has to guess.
- **Verify claimed user words.** A sub-agent's report once said it had received the user's own words, which the main line couldn't see in its conversation. Treat any "the user said …" in an agent report as unverified until it can be traced to the user's message in the main transcript, or to a quote the main line itself put in that agent's prompt. This matters most for approvals of destructive steps.

## Long-tail round: fact checks, wrap-up, time and usage (added 2026-10)

About 20 analysis/review batches, then a fact-check pass and a wrap-up. Six lessons:

1. **Splitting a big fact check across two agents.** Split by kind (people vs groups) rather than by date range, but expect uneven load and have the heavier side checkpoint per batch. Some facts show up on both sides, so list those clusters up front and give each one a **merge owner**: each side verifies only its own items against L1; the owner merges them into one row and does the cross-checks; the other side writes "cross-side → cluster N". Each side writes its own files, so neither waits for the other. The main line merges with a script and asserts **exactly one row per cluster**. Prefix IDs by batch from the start; two "B1" rows still collided and had to be renamed at merge time.
2. **Running packaging alone takes coordination.** Split the wrap-up into "rerun modules + verify" and "package + check". Before dispatching the second part, check that no other session is busy (`claude agents --json`); if one is, poll every few minutes and report BLOCKED after a set time. Announce on the shared board when packaging starts and ends. Also hold new heavy work when free memory drops below a threshold (2.5 GB on a 16 GB laptop). Both packaging runs done this way finished without being killed.
3. **Pick the model by task type, and pass it explicitly.** Judgment work (merging exclusions, decision log, small note fixes, code fixes) on a strong model at medium effort; mechanical work (rerunning modules, verify, package, commit) on a cheaper model at medium effort; fact checks against raw data at high effort. Wrap-up batches on this setup needed zero rework. Usage limits are shared by the whole machine, so a batch's "usage before → after" includes whatever other sessions did meanwhile. Use those numbers as a rough guide only.
4. **Self-reported durations are unreliable.** Analysis agents reported 60–80 minutes; timestamps (scratch folder created → report written) showed 13–21 minutes, 3.5–5× less. Ask agents to write system timestamps at start and end, and use those in logs and decision records.
5. **Too many parallel agents is what burns the usage limit.** Going past the cap (5+ heavy agents at once) hit the 5-hour limit within hours; holding to 3 finished 8 batches in 45 minutes without hitting it.
6. **Small Windows traps in wrap-up scripts.** Windows PowerShell 5.1 misreads a BOM-less `.ps1` with CJK paths, so a sequential runner silently did nothing; use a Python runner instead. Before deleting scratch folders, copy the small helper scripts you may want again to a backup folder.

## Closing a project: parallel write-back, one round of questions, backup check (added 2026-10)

The closing round wrote the user's checked facts into the fact table, the timeline, the knowledge base and a private records folder, then ran an independent check, a rebuild and a close-out report. Four lessons:

1. **Split writers by file zone, not by topic.** Three writers ran at once: one for the project repo (fact table, timeline, notes), one for the knowledge-base notes the checklist pointed to, one for the knowledge-base backfill table, family notes and personal records. Each checklist row's "destination" column decides the owner; each writer re-scans the whole checklist at the end to confirm every row it should take is done. Two of them committed to the same knowledge-base repo at the same time without conflict, because each staged files one by one (`git add -- <file>`) and checked `git status` / `git log` before committing. All three finished in 7–21 minutes.
2. **Expect the permission classifier on personal-data edits.** Changing a cell in a table that holds personal records was blocked (personal-data handling). The writer stopped and handed it back, which was correct. Put the user's own words at the top of any prompt that writes personal records, and compare personal values with code that only prints match / no match.
3. **Ask the user once, at the end.** Each writer listed open questions it couldn't settle from the data (about 20 in total); the coordinator ranked them by how much an answer would improve the knowledge base and asked 12 plus 1 housekeeping question in one message. The user answered all 13 in one round and every answer was written back. This beats asking piecemeal during the work.
4. **Check backup coverage before calling it done.** Only at close did anyone check that the project folder (including the AI notes, a git repo with no remote) and the rebuilt package sat outside both the offline backup and cloud sync, while the raw export was backed up. The notes were only about 15 MB. Decide at kickoff where the AI-written assets are backed up, and put "are the analysis assets backed up?" on the close-out checklist.
