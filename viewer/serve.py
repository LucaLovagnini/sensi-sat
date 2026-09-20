"""A local dev server that supports HTTP Range requests.

`python -m http.server` will not do. A Cloud-Optimized GeoTIFF is read by asking
for byte ranges — the header first, then only the tiles on screen — and Python's
stock handler ignores the `Range` header and returns the whole file with a 200.
geotiff.js treats that as a failure, so the map stays empty with
"AggregateError: Request failed" and nothing more helpful.

That is not a quirk of local testing: range support is the single requirement the
real host has to meet, and every static host we would use (Cloudflare R2, S3 +
CloudFront, GitHub Pages) provides it. This server exists so the thing you develop
against behaves like the thing you deploy to.

    python viewer/serve.py            # then open http://127.0.0.1:8777/viewer/
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import re
import socketserver
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler plus single-range support and permissive CORS."""

    # HTTP/1.1 so connections stay alive. geotiff.js opens several range requests
    # in parallel to read a COG's header, directories and tiles; on HTTP/1.0 each
    # one needs a fresh connection and they fail as "AggregateError: Request
    # failed" with no indication that the protocol version is the reason.
    protocol_version = "HTTP/1.1"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def send_head(self):
        if "Range" not in self.headers:
            return super().send_head()

        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        size = os.fstat(f.fileno()).st_size
        match = RANGE_RE.match(self.headers["Range"])
        if not match:
            f.close()
            self.send_error(400, "Malformed Range header")
            return None

        start_s, end_s = match.groups()
        if start_s:
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
        else:                                   # suffix range: bytes=-N
            length = int(end_s or 0)
            start, end = max(0, size - length), size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            f.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None

        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        f.seek(start)
        return _Slice(f, end - start + 1)

    def log_message(self, fmt, *args):      # one line per request is enough
        if "favicon" not in (args[0] if args else ""):
            super().log_message(fmt, *args)


class _Slice:
    """A file-like object exposing only the requested byte range."""

    def __init__(self, fh, length: int):
        self.fh, self.remaining = fh, length

    def read(self, amount: int = -1) -> bytes:
        if self.remaining <= 0:
            return b""
        if amount is None or amount < 0:
            amount = self.remaining
        chunk = self.fh.read(min(amount, self.remaining))
        self.remaining -= len(chunk)
        return chunk

    def close(self) -> None:
        self.fh.close()


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    handler = functools.partial(RangeHandler, directory=str(ROOT))
    with Server((args.host, args.port), handler) as httpd:
        print(f"serving {ROOT} with Range support")
        print(f"  open http://{args.host}:{args.port}/viewer/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
