# hdx-cod-ab-ai

An agentic workspace for turning raw administrative boundary data from a national source
authority into a validated [COD-AB](https://github.com/OCHA-DAP/hdx-cod-ab-spec) release,
using [Claude Code](https://claude.com/claude-code) as the processing engine.

[`CLAUDE.md`](CLAUDE.md) is the actual playbook: it defines the full pipeline (schema mapping,
changelog comparison, p-code assignment, topology cleaning, attribute derivation, validation,
packaging) as a series of stages Claude runs, with explicit gates where a human confirms a
decision before moving on. This README only covers how to set the workspace up; read
`CLAUDE.md` for how the pipeline itself works.

## Prerequisites

- [VS Code](https://code.visualstudio.com/) with the
  [Claude Code extension](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code)
  installed — this is the intended way to work in this repo. (The
  [Claude Code CLI](https://claude.com/claude-code) also works standalone in a terminal, if you
  prefer that over VS Code.)
- [uv](https://docs.astral.sh/uv/) — Python dependency/venv management
- [DuckDB](https://duckdb.org/) with the `spatial` extension — all data inspection and transformation
- [GDAL](https://gdal.org/) (the modern `gdal` CLI, e.g. `gdal vector convert`) — final format export
- Optional: a browser, for [tools.fieldmaps.io](https://tools.fieldmaps.io/) (Topology Cleaner,
  Edge Extender, Changelog) — or its CLI equivalent, [`topo-tools`](https://pypi.org/project/topo-tools/)

## Getting started

1. Install dependencies: `uv sync`

2. Create a country working directory and drop in the raw source files (any spatial format):

   ```bash
   mkdir -p data/{iso3}/raw
   # copy the source authority's shapefiles/GDB/GeoJSON/etc. into data/{iso3}/raw/
   ```

   `{iso3}` is the country's lowercase ISO3 code. `data/` is gitignored — it's a local,
   ephemeral working directory, not part of the repo.

3. Open the Claude Code panel in VS Code (or run `claude` in the integrated terminal) and start
   a session. Claude will detect the country directory, fetch the previous published release
   from HDX for comparison, convert your raw inputs to GeoParquet, and confirm the admin level
   mapping with you before proceeding — see **Session Start** in `CLAUDE.md` for the exact steps.

## Layout

```text
CLAUDE.md          # the pipeline playbook — read this for how processing works
scripts/
  prepare.py       # fetches the HDX reference release, detects versions, converts to GeoParquet
  m49.py           # downloads UN M49 country names in all 6 official UN languages
data/              # gitignored — one working directory per country (data/{iso3}/)
```

Each country directory accumulates a `REPORT.md` as processing progresses — a running log of
decisions made and gates approved, which doubles as the shareable release summary once the
package is final.
