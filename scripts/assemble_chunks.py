#!/usr/bin/env python3
"""
assemble_chunks.py
------------------
Reads a manifest.txt file and assembles numbered part files (part_0001, part_0002, …)
into the final output file declared in the manifest.

manifest.txt format:
    filename=Biohazard_Beta_0.4.5_server_pack.zip
    chunks=10
    total_bytes=971966925

Usage:
    python assemble_chunks.py                         # looks for manifest.txt in CWD
    python assemble_chunks.py --manifest /path/to/manifest.txt
    python assemble_chunks.py --manifest manifest.txt --parts-dir ./parts --out-dir ./output
"""

import argparse
import os
import sys


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
                raise ValueError(f"manifest line {lineno}: no '=' found → {line!r}")
            key, _, value = line.partition("=")
            manifest[key.strip()] = value.strip()

    required = {"filename", "chunks", "total_bytes"}
    missing = required - manifest.keys()
    if missing:
        raise ValueError(f"manifest is missing required keys: {missing}")

    manifest["chunks"] = int(manifest["chunks"])
    manifest["total_bytes"] = int(manifest["total_bytes"])
    return manifest


# ── Assembly ──────────────────────────────────────────────────────────────────

def assemble(manifest: dict, parts_dir: str, out_dir: str) -> None:
    filename    = manifest["filename"]
    num_chunks  = manifest["chunks"]
    total_bytes = manifest["total_bytes"]

    output_path = os.path.join(out_dir, filename)

    print(f"Output file : {output_path}")
    print(f"Chunks      : {num_chunks}")
    print(f"Expected    : {total_bytes:,} bytes")
    print()

    # Verify every part exists before we start writing
    part_paths = []
    missing_parts = []
    for i in range(1, num_chunks + 1):
        part_name = f"part_{i:04d}"
        part_path = os.path.join(parts_dir, part_name)
        if not os.path.isfile(part_path):
            missing_parts.append(part_path)
        else:
            part_paths.append(part_path)

    if missing_parts:
        print("ERROR — the following part files were not found:")
        for p in missing_parts:
            print(f"  {p}")
        sys.exit(1)

    # Stream-concatenate all parts into the output file
    os.makedirs(out_dir, exist_ok=True)

    written = 0
    chunk_size = 1024 * 1024  # 1 MiB read buffer

    with open(output_path, "wb") as out_fh:
        for idx, part_path in enumerate(part_paths, 1):
            part_size = os.path.getsize(part_path)
            part_written = 0

            with open(part_path, "rb") as part_fh:
                while True:
                    buf = part_fh.read(chunk_size)
                    if not buf:
                        break
                    out_fh.write(buf)
                    part_written += len(buf)

            written += part_written
            print(f"  [{idx:>{len(str(num_chunks))}}/{num_chunks}] "
                  f"{os.path.basename(part_path):>12}  "
                  f"{part_size:>12,} bytes  (running total: {written:,})")

    print()

    # ── Byte-count verification ───────────────────────────────────────────────
    actual_bytes = os.path.getsize(output_path)

    print("── Verification ─────────────────────────────────────────────────────")
    print(f"  Expected bytes : {total_bytes:>15,}")
    print(f"  Written bytes  : {written:>15,}")
    print(f"  On-disk bytes  : {actual_bytes:>15,}")

    ok = True

    if written != total_bytes:
        print(f"\n  ✗  BYTE MISMATCH — streamed {written:,} bytes, "
              f"expected {total_bytes:,}  (diff: {written - total_bytes:+,})")
        ok = False
    else:
        print("\n  ✓  Streamed byte count matches manifest.")

    if actual_bytes != total_bytes:
        print(f"  ✗  ON-DISK SIZE MISMATCH — {actual_bytes:,} bytes on disk, "
              f"expected {total_bytes:,}  (diff: {actual_bytes - total_bytes:+,})")
        ok = False
    else:
        print("  ✓  On-disk file size matches manifest.")

    print()
    if ok:
        print(f"✓  Assembly complete → {output_path}")
    else:
        print("✗  Assembly finished but verification FAILED. "
              "Check the part files for corruption or truncation.")
        sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble numbered chunk files into a single output file."
    )
    parser.add_argument(
        "--manifest", default="manifest.txt",
        help="Path to the manifest file (default: manifest.txt in CWD)"
    )
    parser.add_argument(
        "--parts-dir", default=".",
        help="Directory containing the part_XXXX files (default: CWD)"
    )
    parser.add_argument(
        "--out-dir", default=".",
        help="Directory to write the assembled file into (default: CWD)"
    )
    args = parser.parse_args()

    if not os.path.isfile(args.manifest):
        print(f"ERROR — manifest not found: {args.manifest}")
        sys.exit(1)

    print(f"Reading manifest: {args.manifest}")
    manifest = parse_manifest(args.manifest)
    print(f"  filename    = {manifest['filename']}")
    print(f"  chunks      = {manifest['chunks']}")
    print(f"  total_bytes = {manifest['total_bytes']:,}")
    print()

    assemble(manifest, parts_dir=args.parts_dir, out_dir=args.out_dir)


if __name__ == "__main__":
    main()