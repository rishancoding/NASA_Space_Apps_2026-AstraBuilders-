#!/usr/bin/env python3
"""Download the selected public NASA records, without archives or media.

Uses the public endpoints used by NASA's PSI web client. Metadata is cached in
data/raw; the cleaning pipeline creates the small, committable data package.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw"
BASE = "https://psi.nasa.gov"
RECORDS = {
    "PSI-26": ("BASS", "solid_model"),
    "PSI-25": ("BASS-II", "solid_model"),
    "PSI-98": ("Saffire-I", "solid_evidence"),
    "PSI-99": ("Saffire-II", "solid_evidence"),
    "PSI-100": ("Saffire-III", "solid_evidence"),
    "PSI-69": ("FLEX", "droplet_backup"),
    "PSI-68": ("FLEX-2", "research"),
    "PSI-39": ("CFI", "research"),
    "PSI-10": ("Flame Design", "research"),
    "PSI-20": ("BRE", "research"),
    "PSI-21": ("CLD Flame", "research"),
    "PSI-22": ("E-FIELD Flames", "research"),
    "PSI-23": ("s-Flame", "research"),
    "PSI-159": ("CFI-G", "research"),
    "PSI-107": ("SPICE", "research"),
    "PSI-106": ("SLICE", "research"),
    "PSI-102": ("SAME", "research"),
    "PSI-101": ("SAME-R", "research"),
    "PSI-47": ("DAFT", "research"),
}


def get(url: str) -> bytes:
    # curl uses the OS certificate store, including on macOS Python installs
    # whose separate certificate bundle has not been initialized.
    return subprocess.run(["curl", "-fLsS", "--retry", "2", "--max-time", "90", url],
                          check=True, capture_output=True).stdout


def fetch_metadata(record: str) -> None:
    path = RAW / record / "metadata.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = path.read_bytes() if path.exists() else get(f"{BASE}/geode-py/ws/repo/investigations/{record}")
    metadata = json.loads(payload)
    if metadata.get("accession") != record or not metadata.get("title"):
        raise ValueError(f"Unexpected metadata for {record}")
    path.write_bytes(payload)
    print(f"Verified {record}: {metadata.get('investigationAcronym')} — {metadata['title']}", flush=True)


def inventory(record: str, version: int) -> list[dict]:
    path = RAW / record / "inventory.json"
    if not path.exists():
        body = json.dumps({"folder": record + "/", "fileType": "study",
                           "studyId": record, "version": version, "obfuscationcode": ""})
        response = subprocess.run(["curl", "-fLsS", "--retry", "2", "--max-time", "90",
                                   "-H", "Content-Type: application/json", "--data", body,
                                   BASE + "/geode-py/ws/files/v2"], check=True, capture_output=True)
        path.write_bytes(response.stdout)
    def walk(nodes):
        for node in nodes:
            if node.get("files"):
                yield from walk(node["files"])
            elif not node.get("restricted") and node.get("version"):
                yield {"file_name": Path(node["key"]).name, "version": node["version"],
                       "file_size": node.get("bytes_size", 0)}
    return list(walk(json.loads(path.read_text())["files"]))


def download_file(record: str, file: dict) -> dict:
    filename = file["file_name"]
    path = RAW / record / filename
    query = urlencode({"file": filename, "version": file["version"], "redirect": "false"})
    endpoint = f"{BASE}/geode-py/ws/studies/{record}/download?{query}"
    if not path.exists():
        signed_url = get(endpoint).decode().strip().strip('"')
        if not signed_url.startswith("https://"):
            raise ValueError(f"Invalid download response for {filename}")
        payload = get(signed_url)
        path.write_bytes(payload)
    payload = path.read_bytes()
    expected_size = int(file.get("file_size", len(payload)))
    if len(payload) != expected_size:
        raise ValueError(f"File size mismatch for {filename}: {len(payload)} != {expected_size}")
    return {"source_record": record, "filename": filename,
            "file_version": file["version"], "download_url": endpoint,
            "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            "local_path": str(path.relative_to(ROOT))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch_metadata, RECORDS))
    if args.metadata_only:
        return
    tasks = []
    for record in RECORDS:
        metadata = json.loads((RAW / record / "metadata.json").read_text())
        files = metadata.get("experimentalTable", []) + metadata.get("modelingTable", [])
        # Matrices, calibration and readme documents are necessary to interpret
        # BASS units, sample definitions and notes. Proof sheets are imagery.
        if RECORDS[record][1] != "research":
            current_files = inventory(record, metadata["version"])
        else:
            current_files = []
        if record in {"PSI-25", "PSI-26"}:
            files += [f for f in current_files
                      if f["file_name"].lower().endswith((".xlsx", ".xls", ".csv", ".docx"))
                      and "engineering" not in f["file_name"].lower()]
        files += [f for f in current_files if any(term in f["file_name"].lower() for term in
                  ("bass-ii summary report.pdf", "saffire-i and saffire-iii readme.docx",
                   "saffire objectives, development and status.pdf", "flex dod.docx", "flex_test_plan.pdf"))]
        seen = set()
        for file in files:
            if file["file_name"] not in seen:
                tasks.append((record, file))
                seen.add(file["file_name"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        manifest = list(pool.map(lambda task: download_file(*task), tasks))
    ntrs_url = "https://ntrs.nasa.gov/api/citations/20110008636/downloads/20110008636.pdf"
    path = RAW / "NTRS-20110008636/20110008636.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(get(ntrs_url))
    payload = path.read_bytes()
    manifest.append({"source_record": "NTRS-20110008636", "filename": path.name,
                     "file_version": "", "download_url": ntrs_url, "size_bytes": len(payload),
                     "sha256": hashlib.sha256(payload).hexdigest(), "local_path": str(path.relative_to(ROOT))})
    (RAW / "downloads.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Downloaded {len(manifest)} tables and supporting documents; no media or bulk archives.")


if __name__ == "__main__":
    main()
