#!/usr/bin/env python3
"""Build the curated data package offline from checksummed NASA source files."""
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import warnings
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from openpyxl import load_workbook
from pypdf import PdfReader
import pdfplumber

from fetch_sources import RECORDS, ROOT, RAW
from ground_reference import ground_rows

CLEAN = ROOT / "data/clean"
OBS_COLUMNS = [
    "experiment_id", "source_record", "investigation_name", "test_id", "as_run_test_id",
    "sample_id", "split_group", "test_date", "principal_investigator", "gravity_regime",
    "material", "material_raw", "material_basis", "material_category", "sample_geometry",
    "thickness_mm", "diameter_mm", "width_mm", "oxygen_pct", "oxygen_final_pct",
    "airflow_cm_s", "airflow_raw", "fan_display_raw", "flow_restrictor_raw", "flow_direction",
    "pressure_kpa", "co2_initial_pct", "co2_final_pct", "co_initial_ppm_raw", "co_final_ppm_raw",
    "outcome", "burned_binary", "training_eligible", "label_status", "notes", "quality_flags",
    "source_file", "source_row", "supplement_file", "supplement_locator", "source_url",
]


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def read_csv(path: Path) -> tuple[list[str], list[dict], str]:
    payload = path.read_bytes()
    try:
        body, encoding = payload.decode("utf-8-sig"), "utf-8-sig"
    except UnicodeDecodeError:
        body, encoding = payload.decode("cp1252"), "cp1252"
    reader = csv.DictReader(io.StringIO(body))
    columns = list(reader.fieldnames or [])
    if not columns or len(columns) != len(set(columns)):
        raise ValueError(f"Missing or duplicate headers in {path}")
    rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError(f"Ragged CSV in {path}")
    return columns, rows, encoding


def text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value).strip()


def scalar(value):
    """Only a single decimal, never a range, inequality, or setting list."""
    value = text(value)
    return float(value) if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value) else ""


def date(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text(value), fmt).date().isoformat()
        except ValueError:
            pass
    return text(value)


def workbook(path: Path):
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="wmf image format")
        return load_workbook(path, data_only=True)


def record_url(record: str) -> str:
    return f"https://psi.nasa.gov/physci/repo/data/investigations/{record}"


def dimensions(description: str, geometry: str) -> dict:
    s = description.lower()
    result = {"thickness_mm": "", "diameter_mm": "", "width_mm": ""}
    if geometry == "rod":
        match = re.search(r'(1/4|3/8|1/2|0\.5)\s*"?', s)
        if match:
            result["diameter_mm"] = {"1/4": 6.35, "3/8": 9.525, "1/2": 12.7, "0.5": 12.7}[match[1]]
    elif geometry in {"sphere", "spherical_section"}:
        match = re.search(r"(\d+(?:\.\d+)?)\s*cm", s)
        if match:
            result["diameter_mm"] = float(match[1]) * 10
    elif geometry in {"fabric", "film", "slab", "sheet"}:
        match = re.search(r"(\d+(?:\.\d+)?)\s*micron", s)
        if match:
            result["thickness_mm"] = float(match[1]) / 1000
        else:
            match = re.search(r"(\d+(?:\.\d+)?)\s*mm", s)
            if match:
                result["thickness_mm"] = float(match[1])
        match = re.search(r"(\d+(?:\.\d+)?)\s*cm", s)
        if match:
            result["width_mm"] = float(match[1]) * 10
    return result


def material_info(raw: str, record: str, pi: str) -> dict:
    s, basis = raw.lower(), "sample description"
    if "pmma" in s:
        material = "PMMA"
    elif "sibal" in s:
        material = "SIBAL (cotton/fiberglass)"
    elif "nomex" in s:
        material = "Nomex"
    elif "ultem" in s:
        material = "Ultem (PEI)"
    elif "japan" in s and "wax" in s:
        material = "Japan wax"
    elif "paraffin" in s or "parrafin" in s:
        material = "Paraffin wax"
    elif record == "PSI-25" and pi in {"Bhattacharjee", "Miller", "Olson", "Fernandez-Pello"}:
        material, basis = "PMMA", "BASS-II ReadMe: PI sample definitions"
    elif record == "PSI-25" and "spherical section" in s:
        material, basis = "PMMA", "BASS-II ReadMe: T'ien PMMA spherical-section samples"
    else:
        material = "Unresolved material"
    geometry = next((g for term, g in [("spherical section", "spherical_section"), ("sphere", "sphere"),
                        ("rod", "rod"), ("candle", "candle"), ("film", "film"),
                        ("slab", "slab"), ("sheet", "sheet")] if term in s), "unknown")
    if "sibal" in s or "nomex" in s:
        geometry = "fabric"
    if record == "PSI-25" and geometry == "unknown":
        geometry = {"Bhattacharjee": "film", "Miller": "slab"}.get(pi, "unknown")
    category = "fabric" if geometry == "fabric" else "wax" if "wax" in material.lower() else "polymer" if material in {"PMMA", "Ultem (PEI)"} else "unknown"
    return {"material": material, "material_raw": raw, "material_basis": basis,
            "material_category": category, "sample_geometry": geometry, **dimensions(raw, geometry)}


def bass_supplement() -> dict:
    path = next((RAW / "PSI-26").glob("*As Run*.xlsx"))
    sheet = workbook(path)["as run matrix"]
    result, rows = {}, []
    for rownum, v in enumerate(sheet.values, 1):
        if rownum <= 3 or v[3] is None or v[5] is None:
            continue
        # Science columns only. Other workbook tabs duplicate these tests;
        # camera settings and operational headers are not project data.
        r = {"test_date": date(v[0]), "as_run_test_id": text(v[2]),
             "test_id": text(v[3]), "sample_id": text(v[4]), "material_raw": text(v[5]),
             "igniter_raw": text(v[6]), "flow_restrictor_raw": text(v[7]),
             "fan_display_raw": text(v[9]), "airflow_raw": text(v[10]),
             "nitrogen_pot_raw": text(v[13]), "nitrogen_display_raw": text(v[14]),
             "oxygen_fraction_raw": text(v[26]), "pressure_atm_raw": text(v[27]),
             "co2_mmhg_raw": text(v[28]), "notes": text(v[29]), "source_row": rownum}
        key = (r["test_date"], r["as_run_test_id"], r["test_id"], r["sample_id"])
        if key in result:
            raise ValueError(f"Duplicate BASS test key {key}")
        result[key] = r
        rows.append(r)
    write_csv(CLEAN / "source_tables/BASS_as_run_science.csv", rows, list(rows[0]))
    return result


def bassii_supplement() -> dict:
    path = next((RAW / "PSI-25").glob("*Summary Report.pdf"))
    result = {}
    with pdfplumber.open(path) as pdf:
        # Appendix A, PDF pages 111–121 (printed pages 103–113).
        for pagenum in range(111, 122):
            for table in pdf.pages[pagenum - 1].extract_tables():
                for row in table[1:]:
                    ids = [x for x in row if x and re.fullmatch(r"[BFMOPT]\d+[ab]?", x)]
                    if not ids:
                        continue
                    test_id = ids[0]
                    if test_id in result:
                        raise ValueError(f"Duplicate report test {test_id}")
                    result[test_id] = {"test_id": test_id, "pdf_page": pagenum,
                        "flow_direction": next((x.lower() for x in row if x and x.lower() in
                                               {"concurrent", "opposed", "stagnation"}), ""),
                        "notes": " ".join((row[-1] or "").split())}
    write_csv(CLEAN / "source_tables/BASS_II_report_observations.csv", list(result.values()),
              ["test_id", "pdf_page", "flow_direction", "notes"])
    return result


def export_bassii_matrix() -> None:
    """Retain scientific spreadsheet values alongside NASA's CSV rendering."""
    path = next((RAW / "PSI-25").glob("*Test.Matrices.xlsx"))
    rows = []
    for sheet in workbook(path):
        for rownum, v in enumerate(sheet.values, 1):
            if rownum == 1 or v[2] is None:
                continue
            rows.append({"source_file": path.name, "sheet": sheet.title, "source_row": rownum,
                         "test_date": date(v[0]), "gmt_raw": text(v[1]), "test_id": text(v[2]),
                         "sample_id": text(v[3]), "material_raw": text(v[4]),
                         "flow_restrictor_raw": text(v[5]), "fan_display_raw": text(v[6]),
                         "airflow_raw": text(v[7]), "oxygen_initial_pct_raw": text(v[10]),
                         "oxygen_final_pct_raw": text(v[11]), "co2_initial_pct_raw": text(v[12]),
                         "co2_final_pct_raw": text(v[13]), "co_initial_ppm_raw": text(v[14]),
                         "co_final_ppm_raw": text(v[15])})
    write_csv(CLEAN / "source_tables/BASS_II_matrix_science.csv", rows, list(rows[0]))


def build_solids(tables: dict) -> tuple[list[dict], list[dict]]:
    bass, bassii = bass_supplement(), bassii_supplement()
    rows, exclusions, matched_bass = [], [], set()
    for record in ["PSI-26", "PSI-25"]:
        filename, raw_rows = tables[record][0]
        for rownum, raw in enumerate(raw_rows, 2):
            if "soot cleaning" in raw["Fuel Sample Material"].lower():
                exclusions.append({"source_record": record, "source_file": filename,
                                   "source_row": rownum, "reason": "Soot-cleaning operation, not a material test"})
                continue
            row = dict.fromkeys(OBS_COLUMNS, "")
            row.update(source_record=record, investigation_name=RECORDS[record][0],
                       test_id=raw["Test #"], as_run_test_id=raw.get("As Run Test #", ""),
                       sample_id=raw["Sample #"], test_date=date(raw["Date"]),
                       principal_investigator=raw.get("PI", ""), gravity_regime="microgravity",
                       source_file=filename, source_row=rownum, source_url=record_url(record),
                       outcome="unreviewed", training_eligible="false", label_status="requires_annotation")
            row["experiment_id"] = f"{record}:{row['test_date']}:{row['test_id']}:{row['as_run_test_id']}"
            row["split_group"] = f"{record}:sample:{row['sample_id'].lower()}"
            row.update(material_info(raw["Fuel Sample Material"], record, row["principal_investigator"]))
            flags = []
            if record == "PSI-26":
                key = (row["test_date"], row["as_run_test_id"], row["test_id"], row["sample_id"])
                supplement = bass.get(key)
                if supplement is None:
                    raise ValueError(f"BASS row has no matching as-run source: {key}")
                matched_bass.add(key)
                row.update({k: supplement[k] for k in ["notes", "airflow_raw", "fan_display_raw", "flow_restrictor_raw"]})
                oxygen, pressure = scalar(supplement["oxygen_fraction_raw"]), scalar(supplement["pressure_atm_raw"])
                row["oxygen_pct"] = round(oxygen * 100, 8) if oxygen != "" else ""
                row["pressure_kpa"] = round(pressure * 101.325, 8) if pressure != "" else ""
                row["supplement_file"] = next((RAW / record).glob("*As Run*.xlsx")).name
                row["supplement_locator"] = f"as run matrix!row {supplement['source_row']}"
                co2 = scalar(supplement["co2_mmhg_raw"])
                if co2 != "" and pressure != "" and pressure > 0:
                    row["co2_initial_pct"] = round(co2 / (pressure * 760) * 100, 8)
            else:
                def get(name):
                    return next((v for k, v in raw.items() if k.strip() == name), "")
                row.update(oxygen_pct=scalar(get("Calibrated  initial O2 % by vol")),
                           oxygen_final_pct=scalar(get("Calibrated final O2 % by vol")),
                           airflow_raw=get("Air display"), fan_display_raw=get("Fan display"),
                           flow_restrictor_raw=get("Flow restrictor"),
                           co2_initial_pct=scalar(get("Initial CO2 % by vol")),
                           co2_final_pct=scalar(get("Final CO2 % by vol")),
                           co_initial_ppm_raw=get("Initial CO (ppm)"), co_final_ppm_raw=get("Final CO (ppm)"))
                if row["test_id"] in bassii:
                    supplement = bassii[row["test_id"]]
                    row.update(notes=supplement["notes"], flow_direction=supplement["flow_direction"],
                               supplement_file=next((RAW / record).glob("*Summary Report.pdf")).name,
                               supplement_locator=f"PDF page {supplement['pdf_page']}; Appendix A; test {row['test_id']}")
                else:
                    flags.append("no_report_observation")
                if row["oxygen_final_pct"] != "" and row["oxygen_pct"] != "" and row["oxygen_final_pct"] > row["oxygen_pct"] + 2:
                    flags.append("oxygen_final_increase_requires_review")
            row["airflow_cm_s"] = scalar(row["airflow_raw"])
            if row["airflow_cm_s"] == "" and row["airflow_raw"]:
                flags.append("airflow_sequence_or_qualifier")
            if row["pressure_kpa"] == "":
                flags.append("pressure_not_recorded")
            if row["material"] == "Unresolved material":
                flags.append("material_requires_review")
            row["quality_flags"] = "|".join(flags)
            rows.append(row)
    if matched_bass != set(bass):
        raise ValueError("Some as-run tests were not reconciled to the BASS experimental table")
    # Reconcile unnamed samples only to explicit descriptions of the same
    # physical sample in the same investigation. Do not infer from shape alone.
    sample_materials = {}
    for row in rows:
        if row["material"] != "Unresolved material":
            sample_materials.setdefault(row["split_group"], set()).add(row["material"])
    for row in rows:
        candidates = sample_materials.get(row["split_group"], set())
        if row["material"] == "Unresolved material" and len(candidates) == 1:
            row["material"] = next(iter(candidates))
            row["material_basis"] = "Explicit material description for same source_record and sample_id"
            row["material_category"] = "polymer" if row["material"] == "PMMA" else "wax" if "wax" in row["material"].lower() else "unknown"
            row["quality_flags"] = "|".join(f for f in row["quality_flags"].split("|") if f != "material_requires_review")
    return rows, exclusions


def build_flex(tables: dict) -> list[dict]:
    filename, rows = tables["PSI-69"][0]
    result = []
    for rownum, row in enumerate(rows, 2):
        pressure = scalar(row["Ambient pressure; mmHg"])
        oxygen = scalar(row["O initial ambient composition; mole fraction"])
        result.append({"experiment_id": f"PSI-69:{row['FLEX Test #']}:{row['FLEX Identifier']}", "source_record": "PSI-69",
                       "flex_identifier": row["FLEX Identifier"], "split_group": f"PSI-69:identifier:{row['FLEX Identifier']}",
                       "test_id": row["FLEX Test #"], "fuel": row["Fuel"], "test_date": date(row["Test Date"]),
                       "gravity_regime": "microgravity", "pressure_kpa": round(pressure * 101.325 / 760, 8) if pressure != "" else "",
                       "oxygen_pct": oxygen * 100 if oxygen != "" else "",
                       "nitrogen_fraction": scalar(row["N initial ambient composition; mole fraction"]),
                       "co2_fraction": scalar(row["CO initial ambient composition; mole fraction"]),
                       "helium_fraction": scalar(row["He initial ambient composition; mole fraction"]),
                       "droplet_diameter_mm": scalar(row["Droplet initial diameter; mm"]),
                       "extinction_diameter_mm": scalar(row["Visible flame extinction diameter; mm"]),
                       "burn_time_s": scalar(row["Burn time; s"]), "test_end_raw": row["Test end"],
                       "burning_rate_raw": row["Burning rate; mm"],
                       "burning_rate_unit_status": "NASA CSV header says mm; verify intended d-squared-law units before modeling",
                       "role": "droplet_backup_only", "source_file": filename, "source_row": rownum,
                       "source_url": record_url("PSI-69")})
    return result


def build() -> None:
    CLEAN.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((RAW / "downloads.json").read_text())
    for source in manifest:
        path = ROOT / source["local_path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"Source checksum mismatch: {path}")
    tables, table_index, chunks, catalog, publications = {}, [], [], [], []

    def chunk(record, filename, locator, body, kind):
        for index, start in enumerate(range(0, len(body), 2200)):
            excerpt = body[start:start + 2200]
            if not excerpt.strip():
                continue
            key = f"{record}|{filename}|{locator}|{index}"
            chunks.append({"chunk_id": hashlib.sha256(key.encode()).hexdigest()[:20],
                           "source_record": record, "source_file": filename, "locator": locator,
                           "kind": kind, "source_url": record_url(record) if record.startswith("PSI") else "https://ntrs.nasa.gov/citations/20110008636",
                           "text": excerpt})

    for record, (expected, role) in RECORDS.items():
        metadata = json.loads((RAW / record / "metadata.json").read_text())
        entry = {"source_record": record, "investigation_name": expected, "official_acronym": metadata["investigationAcronym"],
                 "official_title": metadata["title"], "role": role, "version": metadata["version"],
                 "doi": metadata.get("doi", ""), "license": metadata.get("licenseIdentifier", ""),
                 "project_type": metadata.get("projectType", ""), "verification_status": "verified_nasa_metadata",
                 "url": record_url(record), "objective": metadata.get("objective", ""),
                 "approach": metadata.get("approach", ""), "table_count": len(metadata.get("experimentalTable", []))}
        entry["fuel_phase"] = "solid" if role in {"solid_model", "solid_evidence"} else "liquid_droplet" if record in {"PSI-69", "PSI-68", "PSI-39"} else "smoke_aerosol" if record in {"PSI-101", "PSI-102", "PSI-47"} else "gas"
        entry["primary_materials"] = ""
        entry["measured_variables"] = ""
        catalog.append(entry)
        for field in ["title", "description", "objective", "approach", "hypothesis", "researchImpacts"]:
            body = metadata.get(field, "")
            if isinstance(body, str):
                chunk(record, "NASA PSI metadata", field, body, "investigation_metadata")
        for pub in metadata.get("publications", []):
            publications.append({"source_record": record, "title": pub.get("title", ""),
                                 "authors": pub.get("authorList", ""), "doi": pub.get("doi", ""),
                                 "url": "https://doi.org/" + pub["doi"] if pub.get("doi") else record_url(record)})
        tables[record] = []
        for file in metadata.get("experimentalTable", []):
            filename = file["file_name"]
            columns, rows, encoding = read_csv(RAW / record / filename)
            write_csv(CLEAN / "source_tables" / filename, rows, columns)
            tables[record].append((filename, rows))
            table_index.append({"source_record": record, "file": "source_tables/" + filename,
                                "row_count": len(rows), "original_encoding": encoding,
                                "columns": columns, "role": role, "file_version": file["version"]})
        entry["measured_variables"] = " | ".join(dict.fromkeys(k.strip() for _, rows in tables[record] for row in rows[:1] for k in row))
        entry["primary_materials"] = " | ".join(sorted({v.strip() for _, rows in tables[record] for row in rows
            for k, v in row.items() if k.strip().lower() in {"material", "fuel", "fuel sample material"} and v.strip()}))
    ground = ground_rows()
    external = dict.fromkeys(catalog[0], "")
    external.update(source_record="NTRS-20110008636", investigation_name="White Sands ground tests",
                    official_title="Selected Parametric Effects on Materials Flammability Limits", role="earth_comparison",
                    license="US Government work; public use permitted", project_type="Ground investigation",
                    verification_status="verified_nasa_report_tables_2_to_9", url="https://ntrs.nasa.gov/citations/20110008636",
                    objective="Ground flammability thresholds under different ignition, thickness, hardness, mounting, burn-length and geometry configurations.",
                    fuel_phase="solid", primary_materials=" | ".join(sorted({r['material'] for r in ground})),
                    measured_variables="ULOI oxygen volume percent | MOC oxygen volume percent | sample configuration",
                    table_count=8)
    catalog.append(external)
    write_csv(CLEAN / "investigation_catalog.csv", catalog, list(catalog[0]))
    write_csv(CLEAN / "publications.csv", publications, ["source_record", "title", "authors", "doi", "url"])
    write_json(CLEAN / "table_index.json", table_index)
    write_csv(CLEAN / "ground_thresholds.csv", ground, list(ground[0]))
    solids, excluded = build_solids(tables)
    export_bassii_matrix()
    write_csv(CLEAN / "solid_combustion_model.csv", solids, OBS_COLUMNS)
    review_rows = [{"experiment_id": r["experiment_id"], "test_id": r["test_id"], "source_record": r["source_record"],
                   "source_url": r["source_url"], "source_locator": r["supplement_locator"], "notes": r["notes"],
                   "target_name": "", "target_value": "", "condition_airflow_cm_s": "",
                   "condition_oxygen_pct": "", "condition_pressure_kpa": "", "evidence_note": "", "reviewer": "",
                   "review_status": "pending"} for r in solids]
    write_csv(CLEAN / "label_review_queue.csv", review_rows, list(review_rows[0]))
    write_csv(CLEAN / "excluded_rows.csv", excluded, ["source_record", "source_file", "source_row", "reason"])
    flex = build_flex(tables)
    write_csv(CLEAN / "flex_backup.csv", flex, list(flex[0]))
    for source in manifest:
        path, record = ROOT / source["local_path"], source["source_record"]
        if path.suffix == ".pdf":
            for page, obj in enumerate(PdfReader(path).pages, 1):
                chunk(record, path.name, f"PDF page {page}", obj.extract_text() or "",
                      "experiment_plan_text" if "test_plan" in path.name.lower() else "report_text")
        elif path.suffix == ".docx":
            with ZipFile(path) as archive:
                root = ET.fromstring(archive.read("word/document.xml"))
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for number, paragraph in enumerate(root.iter(ns + "p"), 1):
                body = "".join(node.text or "" for node in paragraph.iter(ns + "t"))
                chunk(record, path.name, f"paragraph {number}", body, "document_text")
    with (CLEAN / "evidence_chunks.jsonl").open("w", encoding="utf-8") as f:
        for obj in chunks:
            f.write(json.dumps(obj, ensure_ascii=False, allow_nan=False) + "\n")
    clean_manifest = list(manifest)
    for record in RECORDS:
        path = RAW / record / "metadata.json"
        clean_manifest.append({"source_record": record, "filename": "metadata.json",
            "file_version": json.loads(path.read_text())["version"],
            "download_url": f"https://psi.nasa.gov/geode-py/ws/repo/investigations/{record}",
            "size_bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "local_path": str(path.relative_to(ROOT))})
    write_json(CLEAN / "source_manifest.json", clean_manifest)
    # Calibration values are supporting measurements, not extra training tests.
    cal_path = next((RAW / "PSI-25").glob("*Fan calibration*.xlsx"))
    cal_sheet = workbook(cal_path).worksheets[0]
    cal_cells = [{"source_record": "PSI-25", "source_file": cal_path.name,
                  "sheet": cal_sheet.title, "cell": cell.coordinate, "value": text(cell.value)}
                 for row in cal_sheet for cell in row if cell.value is not None]
    write_csv(CLEAN / "source_tables/BASS_II_fan_calibration_cells.csv", cal_cells,
              ["source_record", "source_file", "sheet", "cell", "value"])
    quality = {
        "schema_version": "1.0.0", "verified_psi_records": len(RECORDS), "external_ntrs_records": 1,
        "experimental_tables": len(table_index), "experimental_table_rows_including_notes": sum(x["row_count"] for x in table_index),
        "solid_observations": len(solids), "solid_rows_by_record": dict(Counter(r["source_record"] for r in solids)),
        "bassii_report_notes": sum(bool(r["notes"]) for r in solids if r["source_record"] == "PSI-25"),
        "bassii_missing_report_notes": [r["test_id"] for r in solids if r["source_record"] == "PSI-25" and not r["notes"]],
        "solid_labeled_rows": 0, "training_eligible_rows": 0,
        "model_readiness": "requires_target_definition_and_reviewed_condition_specific_labels",
        "flex_observations": len(flex), "evidence_chunks": len(chunks), "publications": len(publications),
        "flex_test_end_counts": dict(Counter(r["test_end_raw"] for r in flex)),
        "flex_numeric_burn_times": sum(r["burn_time_s"] != "" for r in flex),
        "ground_threshold_rows": len(ground), "ground_material_families": sorted({r["material"] for r in ground}),
        "missing_values": {k: sum(r[k] == "" for r in solids) for k in ["thickness_mm", "oxygen_pct", "airflow_cm_s", "pressure_kpa"]},
        "quality_flags": dict(Counter(flag for r in solids for flag in r["quality_flags"].split("|") if flag)),
        "limitations": [
            "Extinction after burning is not a no-burn label. No binary target was invented from crew prose.",
            "A single test often changes airflow and reuses a sample. Do not associate its final outcome with only the initial conditions.",
            "Scalar airflow is populated only for a single numeric Air display, whose unit is cm/s per BASS-II ReadMe; fan display is a different signal.",
            "BASS oxygen is a fraction in its workbook despite the percent header; it is multiplied by 100. BASS-II calibrated oxygen is already percent.",
            "BASS pressure is converted from atm to kPa; BASS-II test tables do not record pressure. Do not assume a default.",
            "Some BASS sample descriptions do not name a material. They remain unresolved rather than guessed.",
            "Saffire CSVs retain approximate values, blank material cells, note rows and suspect units verbatim; use their source notes before comparisons.",
            "FLEX is droplet data, kept out of the solid model. Its burning-rate unit needs verification.",
            "Ground thresholds describe Earth-gravity configurations and are not microgravity outcomes.",
            "No validated Moon/Mars prediction, pressure extrapolation, untested material ranking, mass, strength or budget constraints are supplied.",
        ],
    }
    write_json(CLEAN / "quality_report.json", quality)
    units = {"thickness_mm": "mm; nominal description", "diameter_mm": "mm; nominal description",
             "width_mm": "mm; nominal description", "oxygen_pct": "oxygen volume percent",
             "oxygen_final_pct": "oxygen volume percent", "airflow_cm_s": "cm/s; single Air display reading only",
             "pressure_kpa": "kPa", "co2_initial_pct": "CO2 volume percent", "co2_final_pct": "CO2 volume percent"}
    write_json(CLEAN / "data_contract.json", {
        "schema_version": "1.0.0", "null_encoding": "Empty CSV cell; JSON/API numeric null is None/null; never substitute zero",
        "solid_table": "solid_combustion_model.csv", "row_granularity": "One whole BASS or BASS-II test; conditions may vary within a test",
        "primary_key": "experiment_id", "cross_validation_group": "split_group",
        "join_to_catalog": "source_record", "training_gate": "No current row is training eligible; define a target and review condition-specific labels first",
        "columns": {k: {"type": "nullable number" if k in units or k == "burned_binary" else "boolean encoded true/false" if k == "training_eligible" else "string",
                        "unit": units.get(k, ""), "use": "target only after review" if k in {"outcome", "burned_binary"} else "provenance or review; not a feature" if k in {"notes", "quality_flags", "label_status", "source_row", "supplement_locator", "source_url", "source_file", "supplement_file", "co_initial_ppm_raw", "co_final_ppm_raw", "oxygen_final_pct", "co2_final_pct"} else "see DATA_HANDOFF.md"}
                    for k in OBS_COLUMNS},
        "dataset_roles": {"solid_combustion_model.csv": "solid observations and future annotation; no training labels yet",
                          "flex_backup.csv": "liquid droplet fallback only; never pool with solids",
                          "ground_thresholds.csv": "Earth comparison; 70 configuration-specific threshold pairs, not burn outcomes",
                          "source_tables/": "NASA table values; heterogeneous headers, units and note rows",
                          "evidence_chunks.jsonl": "research text with citation locators"},
    })
    from label_data import build_labels
    build_labels()


if __name__ == "__main__":
    build()
