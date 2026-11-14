# Local NASA download cache

From the repository root:

```sh
python3 data/scripts/fetch_sources.py
python3 data/scripts/build_data.py
```

Install the build dependencies from `data/requirements.txt` first. Fetching needs
internet access and `curl`; building is offline. The fetcher caches metadata,
selected tables, readmes and reports by PSI accession, plus the external NTRS
PDF. It does not fetch videos, photos or full archives. Metadata and selected
file versions are recorded in `data/clean/source_manifest.json`.

Existing cached metadata pins a reproducible source version. To request new NASA
versions, use a separate raw cache/checkout and review the resulting changes.
Do not delete the cache simply to rerun cleaning.

This entire cache is ignored by Git. The team can consume `data/clean/` without
the cache, network access or PDF/spreadsheet dependencies. Commit the cleaned
package, scripts, pinned requirements, tests and handoff documentation.
