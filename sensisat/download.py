"""Cached HTTP downloads.

Every dataset in M0 is a public file behind a plain URL. This module is the only
place that touches the network for data, so a notebook can be re-run offline once
the cache is warm, and so every download is recorded (size + checksum) for the
reproducibility requirement in the plan.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

from .config import HTTP_HEADERS, RAW

MANIFEST = RAW / "manifest.json"


@dataclass(frozen=True)
class Asset:
    """A downloaded file and what we know about it."""

    url: str
    path: Path
    bytes: int
    sha256: str
    downloaded_at: str

    def as_record(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path.relative_to(RAW.parent.parent))
        return d


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def _load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {}


def _record(asset: Asset) -> None:
    manifest = _load_manifest()
    manifest[asset.url] = asset.as_record()
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def head(url: str, timeout: int = 30) -> tuple[int, int | None]:
    """(status_code, content_length) without downloading the body."""
    try:
        r = requests.head(url, headers=HTTP_HEADERS, timeout=timeout, allow_redirects=True)
        size = r.headers.get("Content-Length")
        return r.status_code, int(size) if size else None
    except requests.RequestException:
        return 0, None


def fetch(url: str, dest: Path, *, force: bool = False, timeout: int = 600, quiet: bool = False) -> Asset:
    """Download `url` to `dest` unless it is already there. Returns an Asset record.

    Downloads stream to a .part file and are renamed on success, so an interrupted
    run never leaves a truncated file that a later run would trust.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force:
        known = _load_manifest().get(url)
        if known and known.get("bytes") == dest.stat().st_size:
            return Asset(url, dest, known["bytes"], known["sha256"], known["downloaded_at"])
        asset = Asset(url, dest, dest.stat().st_size, _sha256(dest), _now())
        _record(asset)
        return asset

    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, headers=HTTP_HEADERS, timeout=timeout, stream=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        with tmp.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
                got += len(chunk)
                if not quiet and total:
                    pct = 100 * got / total
                    print(f"\r  {dest.name}: {got / 1048576:7.1f} / {total / 1048576:.1f} MiB ({pct:5.1f} %)", end="")
        if not quiet:
            print()
    tmp.replace(dest)

    asset = Asset(url, dest, dest.stat().st_size, _sha256(dest), _now())
    _record(asset)
    return asset


def fetch_json(url: str, timeout: int = 60) -> dict | list:
    r = requests.get(url, headers=HTTP_HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def manifest_table():
    """Downloads so far as a DataFrame — feeds the 'sizes' analysis."""
    import pandas as pd

    rows = list(_load_manifest().values())
    if not rows:
        return pd.DataFrame(columns=["path", "bytes", "MiB", "sha256", "downloaded_at", "url"])
    df = pd.DataFrame(rows)
    df["MiB"] = (df["bytes"] / 1048576).round(2)
    return df[["path", "bytes", "MiB", "sha256", "downloaded_at", "url"]].sort_values("path")
