#!/usr/bin/env python3
"""
reassemble.py
-------------
Reads a manifest.txt and joins all chunk files back into the original file.

Usage:
    python reassemble.py <chunks_folder> [output_folder]

Arguments:
    chunks_folder  – path to the folder containing manifest.txt and part_XXXX files
    output_folder  – where to save the reassembled file (default: current directory)
"""

import sys
import os

def die(msg):
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)

chunks_dir = sys.argv[1].rstrip("/\\")
output_dir = sys.argv[2] if len(sys.argv) >= 3 else "."

manifest_path = os.path.join(chunks_dir, "manifest.txt")
if not os.path.exists(manifest_path):
    die(f"manifest.txt not found in: {chunks_dir}")

# Parse manifest
manifest = {}
with open(manifest_path) as f:
    for line in f:
        line = line.strip()
        if "=" in line:
            k, v = line.split("=", 1)
            manifest[k.strip()] = v.strip()

filename    = manifest.get("filename")
num_chunks  = int(manifest.get("chunks", 0))
total_bytes = int(manifest.get("total_bytes", 0))

if not filename:  die("manifest.txt is missing 'filename'")
if not num_chunks: die("manifest.txt is missing 'chunks'")

print(f"[INFO] File     : {filename}")
print(f"[INFO] Chunks   : {num_chunks}")
print(f"[INFO] Expected : {total_bytes / 1024 / 1024:.2f} MB")

os.makedirs(output_dir, exist_ok=True)
out_path = os.path.join(output_dir, filename)

written = 0
with open(out_path, "wb") as out:
    for i in range(1, num_chunks + 1):
        chunk_path = os.path.join(chunks_dir, f"part_{i:04d}")
        if not os.path.exists(chunk_path):
            die(f"Missing chunk: {chunk_path}")
        with open(chunk_path, "rb") as cf:
            data = cf.read()
        out.write(data)
        written += len(data)
        print(f"[INFO] Merged chunk {i}/{num_chunks} ({written / 1024 / 1024:.2f} MB so far)")

if total_bytes and written != total_bytes:
    print(f"[WARN] Size mismatch: expected {total_bytes} bytes, got {written} bytes", file=sys.stderr)
else:
    print(f"[OK]   Size verified: {written} bytes ({written / 1024 / 1024:.2f} MB)")

print(f"[OK]   Saved to: {out_path}")