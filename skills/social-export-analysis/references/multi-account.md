# Multiple accounts of the same person

Added 2026-10-01. Use this when the user has more than one account on the same platform. Typical reasons: they switched accounts, lost access to the old one, or keep a separate work account.

Each export is a separate dataset, but the people, groups and even individual messages overlap. Account mix-ups silently corrupt conclusions, for example "the old account was still chatting in 2021". Settle the rules below before the first analysis and write them into the project's decision log.

Examples use the made-up accounts **Account A** (old, used until a switch date) and **Account B** (new).

## 1. Three questions, three keys

| Question | Decide by | Don't decide by |
|---|---|---|
| Who sent this message? | The sender alias on the message | Which export it's in, or its date |
| Where did this data come from? | Which export | The sender |
| Which period of the user's life is this? | The date, relative to the switch date | Which export |

- Organize folders by export. That's fine and stable. A self-note sent from Account B to Account A lives in Account A's export folder, but it doesn't mean Account A was in use at that time.
- When you write "Account A did X", count by sender alias. "Messages in Account A's export after the switch date" is a different number, and usually a much bigger one.
- Write the period cutoff precisely, for example "on or before 2020-03-01 = A period, from 2020-03-02 = B period". Decide whether the switch day itself belongs to the old period.

## 2. The old account doesn't go silent on switch day

- After a switch, the old account may still be used for Marketplace sales, replies to job posts, a one-off login, or self-notes to the new account. It may also be lent out, or taken over by a scam ("lend us your account and earn money") and used to spam groups. Date-based attribution therefore fails.
- In the source project, more than half of the old export's messages were dated after the switch. Most came from groups both accounts were in. The old account itself still sent a few hundred messages years later.
- The reverse also happens: the new export contains messages from before the new account existed, because joining a group shows the group's earlier history.
- If the user says "after the switch the old account only received messages", check it with sender counts. Report which part holds and which doesn't, with numbers and categories (for example: mostly true, under 1% of that period's traffic, almost all of it second-hand sales). Ask the user only what the data can't answer: was it them, was the account lent out, was it compromised?

## 3. Alias collisions

- The user's everyday nickname may be the same as an account's display name. For example, people still call the user "Sam" in Account B's chats because Account A was named "Sam Lee". A name mentioned in a note is not an account. In notes, name the account explicitly, for example "Account B (new)".
- Keep two alias sets in config:
  - `self_aliases`: all accounts. Answers "is this the user?" and sets `is_self`.
  - Per-account `aliases`: answers "is this message from this sub-package's own account?". It drives things like which side a chat bubble goes on, and "(my other account)" labels.
- Don't add profile nicknames as sender aliases unless they actually appear as senders. Otherwise a third party with the same name gets counted as the user.
- Aliases set flags. Never let them rewrite the `sender` field.

## 4. Shared threads: count once, analyze once

- The same group or 1:1 thread can appear in both exports, each as a full copy with the same time, sender and text. Detect these "mirror threads" by matching messages verbatim. Name matching alone isn't enough.
- Per-account counts are fine. Cross-account totals must subtract the mirrored messages. Publish all three numbers: A, B, and the overlap or deduplicated total. Never add the A and B columns directly.
- Analyze each shared thread once:
  - Use the more complete side.
  - If both sides are equally complete, use the account where the user actually spoke more.
  - Mark the other side "mirror, see <other account>" in its metadata. Don't delete it.
- Every candidate-ranking step (next-batch candidates, group rankings) must apply the mirror skip. Otherwise the top of the "to do next" list is work that's already done.
- A size cap (for example "skip groups over 30 people") can exclude the more complete side while the smaller side gets analyzed. Record the uncovered period explicitly, for example "covers only from 2019-06 onward".

## 5. Evidence ladder for matching one person across accounts

- **Strong:**
  - The same messages appear in a mirrored group, and the name is unique in both friend lists.
  - System-generated profile fields match (birthday is the hardest to fake).
  - In the new account's chat, the other person calls the user by the old account's nickname.
  - The person was re-friended within a few days of the new account's registration.
  - A group system message says "X added <new account> to the group".
- **Weak:** the same display name only.
- Keep three tiers: confirmed, highly likely, same name only. Never merge "same name only" profiles.

## 6. Checklist before writing anything about an account

1. Which export is this from?
2. Which sender alias sent it?
3. What date range does it cover, relative to the switch date?
4. Is this thread mirrored in the other export? If so, which side is the analyzed one?
5. Did I count by sender (who) or by export (where)? Does the sentence I'm writing match that?
6. Could "the user's name" in this text be a nickname rather than an account?

## 7. Additions from the second round (2026-10-01)

**Group member lists are evidence too.** The same group in both exports should be matched by its stable thread ID suffix plus verbatim-identical messages, not by group name. Once groups are matched, a name on **both** member lists of the same group is strong evidence even if that person never spoke. In the source project, one bug in group matching treated the same group as two different groups and under-rated several people.

**User confirmation must override the rule-based tier, both ways:**
- "Yes, same person" → confirmed, even when the only rule evidence is the same name. Record it as its own evidence type ("user confirmed"), so verify can tell it apart from name-only.
- "No, different people" → a separate tier, **different person**. It is not the same as "same name only": the page says "confirmed different", and no merged page or merge hint is offered.
- "Same name, two different people" → allow splitting one name into two rows. Verify checks that every record goes to exactly one row.
- Already-confirmed answers are not overwritten unless forced. Conflicts are skipped and reported.

**Picking the analysis side for a mirrored group, with deterministic tie-breaks:**
1. If only one side already has notes, use that side.
2. Otherwise use the more complete side (counts within 1% are treated as equal).
3. If both are equally complete, use the account where the user spoke more.
4. If still tied, use the account order in config.

Mark the other side `excluded_reason: mirror` and move its notes "out of the denominator" without deleting them. Apply the rule only when both sides are in the candidate pool. If one side was dropped by a size cap, don't mark anything; record the coverage gap instead (see §4).
