/**
 * Range-request shim for SensiSat's static assets.
 *
 * Cloudflare's Workers Assets platform ignores the `Range` header: measured on
 * this site, five consecutive range requests for the first kilobyte of a 1.5 MB
 * COG all returned `200` with the entire file. That breaks the premise the whole
 * project is built on — a Cloud-Optimized GeoTIFF is read by asking for the few
 * kilobytes currently on screen, and geotiff.js fails outright rather than falling
 * back, so no data layer renders at all.
 *
 * This Worker sits in front of the asset store and does the slicing the platform
 * does not: it fetches the asset, honours the `Range` header, and returns a
 * correct `206 Partial Content`. Everything else passes straight through.
 *
 * The full object is read internally to serve a slice, which sounds wasteful but
 * is not: that read is Cloudflare-internal and cached, while the bytes crossing
 * the public internet — the ones that cost money and time — stay small. A visitor
 * renders Tenerife's building layer from about 64 KiB of a 1.5 MB file.
 */

const RANGE = /^bytes=(\d*)-(\d*)$/;

export default {
  async fetch(request, env) {
    const response = await env.ASSETS.fetch(request);
    const range = request.headers.get("Range");

    // Not a range request, or the platform already handled it correctly.
    if (!range || response.status !== 200) {
      return withHeaders(response);
    }

    const match = RANGE.exec(range.trim());
    if (!match) {
      return withHeaders(response);
    }

    const body = await response.arrayBuffer();
    const size = body.byteLength;
    const [, startRaw, endRaw] = match;

    let start;
    let end;
    if (startRaw === "") {
      // A suffix range, "bytes=-500": the LAST 500 bytes. geotiff.js uses this
      // to find a COG's directory without knowing the file length first.
      const length = Number(endRaw || 0);
      start = Math.max(0, size - length);
      end = size - 1;
    } else {
      start = Number(startRaw);
      end = endRaw === "" ? size - 1 : Math.min(Number(endRaw), size - 1);
    }

    if (!Number.isFinite(start) || !Number.isFinite(end) || start > end || start >= size) {
      return new Response(null, {
        status: 416,
        headers: { "Content-Range": `bytes */${size}`, "Accept-Ranges": "bytes" },
      });
    }

    const headers = new Headers(response.headers);
    headers.set("Content-Range", `bytes ${start}-${end}/${size}`);
    headers.set("Content-Length", String(end - start + 1));
    headers.set("Accept-Ranges", "bytes");
    return decorate(new Response(body.slice(start, end + 1), { status: 206, headers }));
  },
};

/** Advertise range support even on plain responses, so clients do not give up early. */
function withHeaders(response) {
  const headers = new Headers(response.headers);
  headers.set("Accept-Ranges", "bytes");
  return decorate(new Response(response.body, { status: response.status, headers }));
}

/**
 * Published layers are immutable: a rebuild writes new bytes under the same name
 * only when the data itself changed, and the catalogue is small. Long, immutable
 * caching on the rasters is guardrail G4 — it lets the CDN answer nearly every
 * request so the origin is touched once per edge, per version.
 */
function decorate(response) {
  const type = response.headers.get("Content-Type") || "";
  if (type.includes("tiff")) {
    response.headers.set("Cache-Control", "public, max-age=31536000, immutable");
  }
  return response;
}
