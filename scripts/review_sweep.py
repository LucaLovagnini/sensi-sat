"""Put the whole existing repository in front of the pull-request reviewer, part by part.

CodeRabbit (see `.coderabbit.yaml`) only reviews pull requests, and a pull request
only shows a *diff*. Code that already exists on `main` is never in a diff, so it is
never reviewed. This script manufactures a diff that contains everything in one part
of the repository:

    sweep/<part>-base   an orphan commit (no parent) whose tree is HEAD minus the part
    sweep/<part>        a commit on top of it whose tree is exactly HEAD

The pull request `sweep/<part>` -> `sweep/<part>-base` therefore adds every file of
the part and nothing else. The base must be an orphan: if it were a child of HEAD,
HEAD would be the merge base, and GitHub diffs from the merge base, so the pull
request would show nothing at all. These pull requests are never merged. Findings
are triaged there; fixes go through ordinary pull requests against `main`.

Nothing here touches the working tree or the index: the trees are built in a
temporary index file with git plumbing.

    python scripts/review_sweep.py --list           # the parts and their files
    python scripts/review_sweep.py --create         # make the local branch pairs
    python scripts/review_sweep.py --create --push  # ...and push them to origin
    python scripts/review_sweep.py --delete         # remove local (and --push: remote)

Parts are sized so one review stays well inside the reviewer's limits: a part is a
few dozen files, not the whole repository at once.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

#: The parts, as pathspecs. Everything the reviewer would read is in exactly one
#: part; what `.coderabbit.yaml` filters out (the bundle, images, the retired GEE
#: prototype) is filtered there, not here, so the diff stays the true tree.
PARTS: dict[str, list[str]] = {
    "package": ["sensisat", "tests", "pyproject.toml", ".githooks", ".claude",
                ".coderabbit.yaml", ".gitignore"],
    "scripts": ["scripts"],
    "viewer": ["viewer", "wrangler.jsonc", "wrangler.preview.jsonc"],
    "docs": ["docs", "CLAUDE.md", "README.md", "CONTRIBUTING.md", "LICENSE",
             "LICENSE-DATA.md"],
}

REPO_URL = "https://github.com/LucaLovagnini/sensi-sat"


def git(*args: str, env: dict | None = None) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True,
                          env=env).stdout.strip()


def files(part: str) -> list[str]:
    out = git("ls-files", "--", *PARTS[part])
    return out.splitlines() if out else []


def tree_without(part: str) -> str:
    """The tree of HEAD with the part's paths removed, built in a throwaway index."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": os.path.join(tmp, "index")}
        git("read-tree", "HEAD", env=env)
        git("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", *PARTS[part], env=env)
        return git("write-tree", env=env)


def create(part: str, head: str) -> tuple[str, str]:
    subject = git("log", "-1", "--format=%h %s", head)
    base = git("commit-tree", tree_without(part), "-m",
               f"sweep base: the repository without '{part}' (at {subject})")
    tip = git("commit-tree", f"{head}^{{tree}}", "-p", base, "-m",
              f"sweep: every file in '{part}' as of {subject}")
    git("branch", "-f", f"sweep/{part}-base", base)
    git("branch", "-f", f"sweep/{part}", tip)
    return base, tip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    act = ap.add_mutually_exclusive_group(required=True)
    act.add_argument("--list", action="store_true")
    act.add_argument("--create", action="store_true")
    act.add_argument("--delete", action="store_true")
    ap.add_argument("--push", action="store_true", help="also push to / delete on origin")
    ap.add_argument("--part", action="append", choices=sorted(PARTS),
                    help="limit to these parts (default: all)")
    args = ap.parse_args()
    parts = args.part or list(PARTS)

    tracked = set(git("ls-files").splitlines())
    covered = {f for p in PARTS for f in files(p)}

    if args.list:
        for p in parts:
            fs = files(p)
            size = sum(os.path.getsize(f) for f in fs if os.path.exists(f))
            print(f"{p:8} {len(fs):4} files {size / 1024:8.0f} KiB")
        left = sorted(tracked - covered)
        print(f"in no part ({len(left)}): {', '.join(left) or '-'}")
        return 0

    if args.delete:
        failed = []
        for p in parts:
            for b in (f"sweep/{p}", f"sweep/{p}-base"):
                subprocess.run(["git", "branch", "-D", b], capture_output=True)
                if args.push and subprocess.run(["git", "push", "-q", "origin", "--delete", b],
                                                capture_output=True).returncode:
                    failed.append(b)
        for b in failed:
            print(f"could not delete origin/{b} — it is still on the remote", file=sys.stderr)
        return 1 if failed else 0

    head = git("rev-parse", "HEAD")
    for p in parts:
        base, tip = create(p, head)
        n = len(files(p))
        print(f"{p:8} {n:4} files  base {base[:8]}  tip {tip[:8]}")
        if args.push:
            # --no-verify: the pre-push hook checks the working tree's figure review,
            # which these branches do not change; they are never merged.
            git("push", "-q", "--no-verify", "-f", "origin",
                f"sweep/{p}-base", f"sweep/{p}")
    print("\nOpen one pull request per part (base <- compare), and never merge them:")
    for p in parts:
        print(f"  {REPO_URL}/compare/sweep/{p}-base...sweep/{p}?expand=1")
    print("If CodeRabbit does not start on its own, comment:  @coderabbitai full review")
    return 0


if __name__ == "__main__":
    sys.exit(main())
