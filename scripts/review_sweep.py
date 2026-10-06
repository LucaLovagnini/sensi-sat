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
from pathlib import Path

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
REPO_SLUG = "LucaLovagnini/sensi-sat"
ROOT = Path(__file__).resolve().parents[1]

# Every variable that tells git WHICH repository, index or object store to use.
# Each one overrides the working directory, and a git hook exports several of them.
GIT_LOCATION_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                     "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                     "GIT_NAMESPACE", "GIT_PREFIX")


def origin_is_ours(url: str) -> bool:
    """Is this remote URL this repository on GitHub — not a fork with a similar name?

    Accepts the forms a clone can have: the SSH alias `github-personal:` (see
    CLAUDE.md, Git), `git@github.com:`, `ssh://git@github.com/` and `https://github.com/`,
    each ending in exactly the slug, with or without `.git` and a trailing slash.
    """
    path = url.strip().removesuffix("/").removesuffix(".git")
    for host in ("github-personal:", "git@github.com:", "ssh://git@github.com/",
                 "https://github.com/"):
        if path.startswith(host):
            return path[len(host):] == REPO_SLUG
    return False


def clean_env(**extra: str) -> dict:
    """The environment without the variables that redirect git to another repository.

    A git hook exports GIT_DIR (and sometimes GIT_WORK_TREE or GIT_INDEX_FILE), and
    those win over the working directory. Run from inside a hook, `--delete --push` would otherwise
    delete branches on *that* repository's origin. `sensisat.facts.data_version`
    was bitten by the same inheritance.
    """
    env = {k: v for k, v in os.environ.items() if k not in GIT_LOCATION_VARS}
    return {**env, **extra}


def git(*args: str, env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    # cwd=ROOT: the repository this script belongs to, wherever it was started from.
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True,
                          env=env or clean_env(), cwd=ROOT)


def out(*args: str, env: dict | None = None) -> str:
    return git(*args, env=env).stdout.strip()


def files(part: str) -> list[str]:
    listed = out("ls-files", "--", *PARTS[part])
    return listed.splitlines() if listed else []


def tree_without(part: str) -> str:
    """The tree of HEAD with the part's paths removed, built in a throwaway index."""
    with tempfile.TemporaryDirectory() as tmp:
        env = clean_env(GIT_INDEX_FILE=os.path.join(tmp, "index"))
        out("read-tree", "HEAD", env=env)
        out("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", *PARTS[part], env=env)
        return out("write-tree", env=env)


def create(part: str, head: str) -> tuple[str, str]:
    subject = out("log", "-1", "--format=%h %s", head)
    base = out("commit-tree", tree_without(part), "-m",
               f"sweep base: the repository without '{part}' (at {subject})")
    tip = out("commit-tree", f"{head}^{{tree}}", "-p", base, "-m",
              f"sweep: every file in '{part}' as of {subject}")
    out("branch", "-f", f"sweep/{part}-base", base)
    out("branch", "-f", f"sweep/{part}", tip)
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

    tracked = set(out("ls-files").splitlines())
    covered = {f for p in PARTS for f in files(p)}

    if args.list:
        for p in parts:
            fs = files(p)
            size = sum((ROOT / f).stat().st_size for f in fs if (ROOT / f).exists())
            print(f"{p:8} {len(fs):4} files {size / 1024:8.0f} KiB")
        left = sorted(tracked - covered)
        print(f"in no part ({len(left)}): {', '.join(left) or '-'}")
        return 0

    if args.push:
        # Every remote write below goes to `origin`; make sure that is this project.
        # A remote can PUSH somewhere other than it fetches from, and to several
        # places at once, so every push URL is checked, not just the fetch URL.
        # The fetch URL is checked too: --delete asks it whether a branch exists
        # before pushing the deletion. `get-url` expands insteadOf/pushInsteadOf,
        # so these are the addresses git will really use.
        urls = [u for flag in ((), ("--push",))
                for u in git("remote", "get-url", "--all", *flag, "origin",
                             check=False).stdout.split()]
        foreign = [u for u in urls if not origin_is_ours(u)]
        if not urls or foreign:
            print(f"origin reaches {', '.join(foreign) or 'nothing'}, not only {REPO_SLUG}"
                  " — refusing to push", file=sys.stderr)
            return 1

    if args.delete:
        # A branch that is already absent counts as deleted; one that is present and
        # survives the delete is a failure, reported and reflected in the exit code.
        failed = []
        for p in parts:
            for b in (f"sweep/{p}", f"sweep/{p}-base"):
                if (git("show-ref", "--verify", "-q", f"refs/heads/{b}", check=False).returncode == 0
                        and git("branch", "-D", b, check=False).returncode):
                    failed.append(b)
                if not args.push:
                    continue
                remote = git("ls-remote", "--heads", "origin", f"refs/heads/{b}", check=False)
                if remote.returncode:
                    # Could not even ask: record it and go on with the other branches.
                    failed.append(f"origin/{b} (could not check: {remote.stderr.strip()})")
                elif (remote.stdout.strip()
                        and git("push", "-q", "origin", "--delete", b, check=False).returncode):
                    failed.append(f"origin/{b}")
        for b in failed:
            print(f"could not delete {b} — it may still exist", file=sys.stderr)
        return 1 if failed else 0

    head = out("rev-parse", "HEAD")
    for p in parts:
        base, tip = create(p, head)
        n = len(files(p))
        print(f"{p:8} {n:4} files  base {base[:8]}  tip {tip[:8]}")
        if args.push:
            # --no-verify: the pre-push hook checks the working tree's figure review,
            # which these branches do not change; they are never merged.
            out("push", "-q", "--no-verify", "-f", "origin",
                f"sweep/{p}-base", f"sweep/{p}")
    print("\nOpen one pull request per part (base <- compare), and never merge them:")
    for p in parts:
        print(f"  {REPO_URL}/compare/sweep/{p}-base...sweep/{p}?expand=1")
    print("If CodeRabbit does not start on its own, comment:  @coderabbitai full review")
    return 0


if __name__ == "__main__":
    sys.exit(main())
