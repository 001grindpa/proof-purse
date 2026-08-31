# GenLayer Bounty Board

A GenLayer Intelligent Contract that escrows a bounty against a public spec and
pays a hunter only when validators agree the work fulfills it.

This is not insurance. A rejected submission does not refund the funder. The
bounty stays reserved and reopens for the next hunter. The funder can cancel
for a 1:1 refund when no review is pending, or after the deadline.

## How it works

1. A funder creates a bounty with spec text, two independent code-host URLs,
   and a GEN amount. That amount is locked as `RESERVED`.
2. A hunter submits two independent work URLs (for example a pull request and
   a commit).
3. Anyone can call `resolve`. Validators fetch all four pages, extract facts
   with an LLM, and accept the result only under `strict_eq`.
4. `ACCEPTED` pays the reserved amount to the hunter. `PARTIAL`, `UNRELATED`,
   and `UNKNOWN` never pay. The bounty returns to `OPEN`.

## Contract API

Source: [BountyBoard.py](BountyBoard.py)

### Constructor

No arguments. The first bounty ID is `"1"`.

### Create a bounty

Payable write:

```text
create_bounty(
  title="Add rate-limit middleware",
  spec_text="PR must add middleware and tests. Closes the linked issue.",
  spec_url_a="https://github.com/org/repo/issues/42",
  spec_url_b="https://github.com/org/repo/blob/main/CONTRIBUTING.md",
  deadline_unix=1770000000
)
```

Attach the bounty amount as the transaction value.

Requirements:
- Non-empty title and spec text
- Two `https://` URLs from trusted code hosts
- Distinct pages; same host is allowed only when the page kinds differ
  (issue, pull, commit, compare, blob, or raw)
- Non-zero amount
- `deadline_unix` in the future, or `0` for no deadline

Trusted hosts: GitHub, GitLab, Bitbucket, Codeberg, and SourceHut
(with or without `www`, plus `raw.githubusercontent.com` and `gist.github.com`).

Returns the new bounty ID as a string.

### Submit work

```text
submit_work(
  "1",
  "https://github.com/org/repo/pull/88",
  "https://github.com/org/repo/commit/abc123"
)
```

- Only while the bounty is `OPEN`
- Not after the deadline
- Not while another submission is `PENDING`
- The funder cannot submit on their own bounty

### Resolve a bounty

```text
resolve("1")
```

`resolve` copies storage into memory, then runs a nondeterministic block under
`gl.eq_principle.strict_eq`:

1. Fetch both spec pages and both work pages with `gl.nondet.web.get`
2. Extract page facts with `gl.nondet.exec_prompt`
3. Judge whether the work fulfills the spec
4. Block `ACCEPTED` if any required page is incomplete or unrelated

Pays the hunter only when `verdict == ACCEPTED`. Otherwise the submission is
marked `REJECTED`, the hunter slot is cleared, and the reserve stays locked.

### Cancel a bounty

```text
cancel("1")
```

Only the funder. Not allowed while a submission is pending, unless the
deadline has passed. Refunds the reserved amount to the funder
(`REFUNDED_TO_FUNDER`).

### View methods

| Method | Returns |
| --- | --- |
| `get_bounty(bounty_id)` | Full bounty JSON, including URLs, reserve, verdict, and `funds_disposition` |
| `get_bounty_status(bounty_id)` | `OPEN`, `PENDING_REVIEW`, `ACCEPTED`, or `CANCELLED` |
| `get_bounty_count()` | Number of bounties created |
| `get_reserved_bounties()` | Sum of amounts still locked |

## Deploy with Studio

1. Open [GenLayer Studio](https://studio.genlayer.com) and paste `BountyBoard.py`.
2. Deploy. There are no constructor inputs.
3. Call `create_bounty` with two trusted spec URLs and a GEN value.
4. From a second account, call `submit_work` with two work URLs.
5. Call `resolve`, then inspect `get_bounty`.

## Deploy with CLI

```bash
genlayer deploy --contract BountyBoard.py
```

Create a bounty:

```bash
genlayer write <contract_address> create_bounty \
  --arg title "Add rate-limit middleware" \
  --arg spec_text "PR must add middleware and tests." \
  --arg spec_url_a "https://github.com/org/repo/issues/42" \
  --arg spec_url_b "https://github.com/org/repo/blob/main/CONTRIBUTING.md" \
  --arg deadline_unix 0 \
  --value "1000000000000000000"
```

Submit work:

```bash
genlayer write <contract_address> submit_work \
  --arg bounty_id "1" \
  --arg work_url_a "https://github.com/org/repo/pull/88" \
  --arg work_url_b "https://github.com/org/repo/commit/abc123"
```

Resolve:

```bash
genlayer write <contract_address> resolve --arg bounty_id "1"
```

Network and wallet flags: [deployment guide](https://docs.genlayer.com/developers/intelligent-contracts/deploying).

## Design notes

- Dual allowlisted pages reduce single-URL manipulation. A hunter cannot point
  both work sources at the same page kind on the same host.
- Eligibility is verdict-gated. `PARTIAL`, `UNRELATED`, and `UNKNOWN` cannot
  pay, even if the model is confident.
- Each open bounty reserves exactly its amount. Accept pays the hunter 1:1.
  Cancel refunds the funder 1:1. The book is solvent if
  `balance >= reserved_bounties`.
- Rejected work does not move funds. That keeps this a bounty board, not a
  refund product.
- LLM output is reduced to canonical JSON so `strict_eq` is meaningful across
  validators.
- Storage values used in the nondeterministic block are copied into local
  memory first.

See the [first contract guide](https://docs.genlayer.com/developers/intelligent-contracts/first-contract),
[storage](https://docs.genlayer.com/developers/intelligent-contracts/storage),
and [Equivalence Principle](https://docs.genlayer.com/developers/intelligent-contracts/equivalence-principle)
documentation for SDK and network details.
