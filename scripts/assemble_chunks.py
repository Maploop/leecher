#!/usr/bin/env python3
"""
assemble_chunks.py
------------------
Downloads numbered part files listed in links.txt, then assembles them
into the final output file declared in manifest.txt.

manifest.txt format:
    filename=Biohazard_Beta_0.4.5_server_pack.zip
    chunks=10
    total_bytes=971966925

links.txt format (one URL per line, in order):
    https://example.com/parts/part_0001
    https://example.com/parts/part_0002
    ...

Usage:
    python assemble_chunks.py
    python assemble_chunks.py --manifest manifest.txt --links links.txt
    python assemble_chunks.py --manifest manifest.txt --links links.txt \
                              --parts-dir ./parts --out-dir ./output
    python assemble_chunks.py --keep-parts   # don't delete parts after assembly
    python assemble_chunks.py --retries 5    # retry failed downloads up to 5 times
"""

"""
Example:

python assemble_chunks.py \
  --manifest meta/manifest.txt \
  --links meta/links.txt \
  --parts-dir /tmp/parts \
  --out-dir ./dist \
  --retries 5 \
  --keep-parts
"""

import argparse
import os
import sys
import time
import urllib.request
import urllib.error


CHUNK_SIZE = 1024 * 1024  # 1 MiB I/O buffer


# ── Manifest parsing ──────────────────────────────────────────────────────────

def parse_manifest(path: str) -> dict:
    """Parse a simple key=value manifest file and return a dict."""
    manifest = {}
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ValueError(f"manifest line {lineno}: no '=' found -> {line!r}")
            key, _, value = line.partition("=")
            manifest[key.strip()] = value.strip()

    required = {"filename", "chunks", "total_bytes"}
    missing = required - manifest.keys()
    if missing:
        raise ValueError(f"manifest is missing required keys: {missing}")

    manifest["chunks"] = int(manifest["chunks"])
    manifest["total_bytes"] = int(manifest["total_bytes"])
    return manifest


# ── Links parsing ─────────────────────────────────────────────────────────────

def parse_links(path: str) -> list:
    """Return a list of URLs from a plain-text file, one URL per line."""
    links = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                links.append(line)
    return links


# ── Download helpers ──────────────────────────────────────────────────────────

def _format_speed(bps: float) -> str:
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bps < 1024:
            return f"{bps:.1f} {unit}"
        bps /= 1024
    return f"{bps:.1f} TB/s"


def _format_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def download_part(url: str, dest_path: str, label: str,
                  retries: int = 3, timeout: int = 60) -> int:
    """
    Download *url* to *dest_path* with a live progress bar.
    Resumes an incomplete file if it already exists on disk.
    Returns the number of bytes written in this session.
    """
    existing = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url)
            if existing:
                req.add_header("Range", f"bytes={existing}-")

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                status = resp.status

                if existing and status == 206:    # server honours Range
                    total += existing
                elif existing and status == 200:  # server ignored Range, restart
                    existing = 0

                written_this_session = 0
                t0 = time.monotonic()

                mode = "ab" if existing else "wb"
                with open(dest_path, mode) as fh:
                    while True:
                        buf = resp.read(CHUNK_SIZE)
                        if not buf:
                            break
                        fh.write(buf)
                        written_this_session += len(buf)

                        # ── Live progress bar ──────────────────────────
                        done    = existing + written_this_session
                        elapsed = max(time.monotonic() - t0, 0.001)
                        speed   = written_this_session / elapsed
                        pct     = (done / total * 100) if total else 0.0
                        bar_w   = 25
                        filled  = int(bar_w * pct / 100)
                        bar     = "#" * filled + "-" * (bar_w - filled)
                        size_str = (
                            f"{_format_bytes(done)}/{_format_bytes(total)}"
                            if total else _format_bytes(done)
                        )
                        print(
                            f"\r  {label}  [{bar}] {pct:5.1f}%  "
                            f"{size_str}  {_format_speed(speed)}   ",
                            end="", flush=True,
                        )

                print()  # newline after progress bar finishes
                return written_this_session

        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            print(f"\n  ! Attempt {attempt}/{retries} failed: {exc}")
            if attempt < retries:
                wait = 2 ** attempt
                print(f"    Retrying in {wait}s ...")
                time.sleep(wait)
                # pick up however many bytes made it to disk
                existing = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
            else:
                raise RuntimeError(
                    f"Failed to download {url} after {retries} attempts."
                ) from exc

    return 0  # unreachable


def download_all(links: list, parts_dir: str,
                 num_chunks: int, retries: int) -> list:
    """Download every URL in *links* and return local part paths in order."""
    if len(links) != num_chunks:
        print(f"ERROR -- links.txt has {len(links)} URL(s) but manifest "
              f"declares {num_chunks} chunks.")
        sys.exit(1)

    os.makedirs(parts_dir, exist_ok=True)
    width = len(str(num_chunks))
    part_paths = []

    print(f"Downloading {num_chunks} part(s) into: {parts_dir}\n")

    for idx, url in enumerate(links, 1):
        part_name = f"part_{idx:04d}"
        dest      = os.path.join(parts_dir, part_name)
        label     = f"[{idx:>{width}}/{num_chunks}] {part_name}"

        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"  {label}  already present "
                  f"({_format_bytes(os.path.getsize(dest))}), skipping.")
        else:
            print(f"  {label}  <- {url}")
            download_part(url, dest, label, retries=retries)

        part_paths.append(dest)

    print()
    return part_paths


# ── Assembly ──────────────────────────────────────────────────────────────────

def assemble(manifest: dict, part_paths: list, out_dir: str) -> None:
    filename    = manifest["filename"]
    num_chunks  = manifest["chunks"]
    total_bytes = manifest["total_bytes"]
    output_path = os.path.join(out_dir, filename)
    width       = len(str(num_chunks))

    print(f"Assembling  : {output_path}")
    print(f"Chunks      : {num_chunks}")
    print(f"Expected    : {total_bytes:,} bytes\n")

    os.makedirs(out_dir, exist_ok=True)

    written = 0
    with open(output_path, "wb") as out_fh:
        for idx, part_path in enumerate(part_paths, 1):
            part_size = os.path.getsize(part_path)
            with open(part_path, "rb") as part_fh:
                while True:
                    buf = part_fh.read(CHUNK_SIZE)
                    if not buf:
                        break
                    out_fh.write(buf)
                    written += len(buf)
            print(f"  [{idx:>{width}}/{num_chunks}] {os.path.basename(part_path):>12}  "
                  f"{part_size:>13,} bytes  (running total: {written:,})")

    print()

    # ── Byte-count verification ───────────────────────────────────────────────
    actual_bytes = os.path.getsize(output_path)

    print("-- Verification -----------------------------------------------------")
    print(f"  Expected bytes : {total_bytes:>15,}")
    print(f"  Written bytes  : {written:>15,}")
    print(f"  On-disk bytes  : {actual_bytes:>15,}")

    ok = True

    if written != total_bytes:
        print(f"\n  FAIL  BYTE MISMATCH -- streamed {written:,} bytes, "
              f"expected {total_bytes:,}  (diff: {written - total_bytes:+,})")
        ok = False
    else:
        print("\n  OK    Streamed byte count matches manifest.")

    if actual_bytes != total_bytes:
        print(f"  FAIL  ON-DISK SIZE MISMATCH -- {actual_bytes:,} bytes on disk, "
              f"expected {total_bytes:,}  (diff: {actual_bytes - total_bytes:+,})")
        ok = False
    else:
        print("  OK    On-disk file size matches manifest.")

    print()
    if ok:
        print(f"Assembly complete -> {output_path}")
    else:
        print("Assembly finished but verification FAILED. "
              "The downloaded parts may be corrupt or truncated.")
        sys.exit(1)


# ── Cleanup ───────────────────────────────────────────────────────────────────

def cleanup_parts(part_paths: list) -> None:
    print("\nCleaning up part files ...")
    for p in part_paths:
        try:
            os.remove(p)
            print(f"  deleted {p}")
        except OSError as exc:
            print(f"  could not delete {p}: {exc}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download chunk files from links.txt and assemble them."
    )
    parser.add_argument(
        "--manifest", default="manifest.txt",
        help="Manifest file (default: manifest.txt)",
    )
    parser.add_argument(
        "--links", default="links.txt",
        help="File with one download URL per line (default: links.txt)",
    )
    parser.add_argument(
        "--parts-dir", default="parts",
        help="Directory to store downloaded parts (default: ./parts)",
    )
    parser.add_argument(
        "--out-dir", default=".",
        help="Directory to write the assembled file into (default: CWD)",
    )
    parser.add_argument(
        "--retries", type=int, default=3,
        help="Download retry attempts per part (default: 3)",
    )
    parser.add_argument(
        "--keep-parts", action="store_true",
        help="Keep part files after successful assembly",
    )
    args = parser.parse_args()

    # ── Validate inputs ───────────────────────────────────────────────────────
    for label, path in [("manifest", args.manifest), ("links", args.links)]:
        if not os.path.isfile(path):
            print(f"ERROR -- {label} file not found: {path}")
            sys.exit(1)

    print(f"Reading manifest : {args.manifest}")
    manifest = parse_manifest(args.manifest)
    print(f"  filename    = {manifest['filename']}")
    print(f"  chunks      = {manifest['chunks']}")
    print(f"  total_bytes = {manifest['total_bytes']:,}\n")

    print(f"Reading links    : {args.links}")
    links = parse_links(args.links)
    print(f"  {len(links)} URL(s) found\n")

    # ── Download ──────────────────────────────────────────────────────────────
    part_paths = download_all(links, args.parts_dir, manifest["chunks"], args.retries)

    # ── Assemble ──────────────────────────────────────────────────────────────
    assemble(manifest, part_paths, args.out_dir)

    # ── Optional cleanup ──────────────────────────────────────────────────────
    if not args.keep_parts:
        cleanup_parts(part_paths)


if __name__ == "__main__":
    main()