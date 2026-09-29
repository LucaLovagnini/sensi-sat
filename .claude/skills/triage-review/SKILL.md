---
name: triage-review
description: Triage the second reviewer's (CodeRabbit's) comments on a SensiSat pull request — verify each claim against the code, then fix, reject with a reason, or park as an issue, reply on the thread and resolve it — so branch protection's "all conversations resolved" means every comment was answered, not dismissed.
---

# /triage-review <PR number> — answer every review thread

Branch protection on `main` requires CodeRabbit's status to have run and every
review thread to be resolved (CLAUDE.md, "Review lifecycle"). GitHub cannot tell a
thread that was answered from one that was clicked away. This skill is the answer.

## 0. Identity first — never a work account

```bash
export GH_TOKEN=$(gh auth token --user LucaLovagnini)   # the personal account, this shell only
gh api user --jq .login        # must print LucaLovagnini
```

The machine's active `gh` login is a work account; the personal one is in the same
keyring and is used per command through `GH_TOKEN`, never by `gh auth switch`. If the
check prints anything else, **stop writing to GitHub**. Reading still works without auth because the repository is
public:

```bash
curl -s "https://api.github.com/repos/LucaLovagnini/sensi-sat/pulls/<N>/comments?per_page=100&page=1"
# ...and page=2, 3, … until a page returns []
```

In that case write every reply into `<scratchpad>/pr-<N>-replies.md` (thread URL,
verdict, reply text) and hand it to Luca to post.

## 1. Read everything before answering anything

**Read every page.** A read that stops at the first page silently drops findings, and
then "every thread answered" is false. Fetch the review threads with their resolution
state (GraphQL, authenticated; `--paginate` follows `endCursor` for you):

```bash
gh api graphql -f query='query($n:Int!, $endCursor:String){repository(owner:"LucaLovagnini",name:"sensi-sat"){
  pullRequest(number:$n){reviewThreads(first:100, after:$endCursor){nodes{id isResolved path line
  comments(first:100){nodes{author{login} body url} pageInfo{hasNextPage}}} pageInfo{hasNextPage endCursor}}}}}' \
  --paginate -F n=<N>
```

`--paginate` follows the outer cursor only. For any thread whose `comments.pageInfo.hasNextPage`
is true, read the rest of that thread before judging it:

```bash
gh api graphql -f query='query($id:ID!, $endCursor:String){node(id:$id){... on PullRequestReviewThread{
  comments(first:100, after:$endCursor){nodes{author{login} body url} pageInfo{hasNextPage endCursor}}}}}' \
  --paginate -F id=<thread id>
```

CodeRabbit also puts findings on lines outside the diff and "nitpicks" in the review
body itself; read the review bodies (`gh api --paginate repos/LucaLovagnini/sensi-sat/pulls/<N>/reviews`) too.

**Fetch once, then work from the files.** Save the threads and review bodies to JSON
in the scratchpad with the token above, and give helpers (subagents, verification
passes) those files instead of GitHub. Unauthenticated GitHub API calls are capped at
a few dozen an hour; every helper of a sweep stalled on that cap, with no error beyond
"no progress". Helpers never need the network to judge a finding.

## 2. For each finding: verify, then one of three verdicts

Verify the claim against the code — reproduce it with a test or a one-off script
where it is cheap. A reviewer's claim is a hypothesis, not a fact.

| verdict | when | reply says |
|---|---|---|
| **fixed** | the defect is real | what was wrong, the commit that fixes it, the test that now guards it |
| **rejected** | the claim is wrong, or the change would make things worse | *why*, with the evidence — the number, the file, the CLAUDE.md item |
| **parked** | real but out of scope | the issue number it now lives in |

Rules specific to this repository:
- **Never "correct" a historical number** to match another (CLAUDE.md #24). A comment
  saying two figures disagree is answered by saying which is live and which is frozen.
- A suggestion to write a number as a word is always rejected (#23).
- A fix that changes a figure goes through the figure gate like any other: `pytest`,
  and `/verify-figures` if the review goes stale.
- Explain the domain in the reply when the finding touches it — the reply is read by
  Luca, who is learning the domain from exactly these exchanges.

## 3. Reply, then resolve

```bash
gh api repos/LucaLovagnini/sensi-sat/pulls/<N>/comments/<comment_id>/replies -f body='…'
gh api graphql -f query='mutation($t:ID!){resolveReviewThread(input:{threadId:$t}){thread{isResolved}}}' -f t=<thread id>
```

Resolve only after the reply is posted. Push fixes first, so the reply can name the commit.

## 4. Teach the reviewer

When the same wrong finding appears a second time, add a sentence to the matching
`path_instructions` entry in `.coderabbit.yaml` saying why it is wrong here. The
reviewer's false positives are a property of our instructions, and fixable there.

## Sweep pull requests

A `sweep/<part>` pull request (`scripts/review_sweep.py`) is never merged. Fixes go
on an ordinary branch with a pull request against `main`; the sweep thread's reply
links that pull request. Close the sweep pull request once every thread is
resolved, then `python scripts/review_sweep.py --delete --push --part <part>`.
