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
gh api user --jq .login        # must print LucaLovagnini
```

Anything else (the machine's default `gh` login is a work account) means **stop
writing to GitHub**. Reading still works without auth because the repository is
public:

```bash
curl -s "https://api.github.com/repos/LucaLovagnini/sensi-sat/pulls/<N>/comments?per_page=100"
```

In that case write every reply into `<scratchpad>/pr-<N>-replies.md` (thread URL,
verdict, reply text) and hand it to Luca to post. Never switch `gh` accounts yourself.

## 1. Read everything before answering anything

Fetch the review threads with their resolution state (GraphQL, authenticated):

```bash
gh api graphql -f query='query($n:Int!){repository(owner:"LucaLovagnini",name:"sensi-sat"){
  pullRequest(number:$n){reviewThreads(first:100){nodes{id isResolved path line
  comments(first:20){nodes{author{login} body url}}}}}}}' -F n=<N>
```

CodeRabbit also puts findings on lines outside the diff and "nitpicks" in the review
body itself; read the review bodies (`gh api repos/LucaLovagnini/sensi-sat/pulls/<N>/reviews`) too.

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
