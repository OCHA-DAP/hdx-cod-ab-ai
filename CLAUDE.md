# COD-AB Data Cleaning Workspace

This workspace processes raw administrative boundary data from a source authority into a
validated COD-AB release. The previous published version is fetched automatically from HDX
and used as a reference baseline. Multiple countries can be in flight simultaneously — all
work is scoped by country directory (e.g. `syr/`, `gab/`).

## Tools

| Tool | Purpose |
| --- | --- |
| [tools.fieldmaps.io](https://tools.fieldmaps.io/) | Topology Cleaner, Edge Extender, Changelog — run in browser |
| DuckDB (spatial ext) | All data inspection, transformation, attribute work, validation |
| uv | All Python scripts (`uv run`); `uv add` for dependencies |
| `prepare.py` | Fetches HDX reference, detects version, converts all inputs to GeoParquet |

DuckDB spatial: `duckdb -c "INSTALL spatial; LOAD spatial; ..."` or use `:memory:` shell.

---

## Session Start

Run this at the start of every session.

### 1. Identify the active country

```bash
ls -d */
```

If multiple countries exist, ask the user which one to work on. Set `{iso3}` = the country
code (e.g. `syr`). The version numbers are derived from the data — `{ref_version}` is the
previous HDX release (e.g. `v02`), `{version}` is the new release being prepared (e.g. `v03`).

### 2. Run prepare.py (if not already done)

Check whether GeoParquet files exist:

```bash
ls {iso3}/
```

If only `raw/` is present (no versioned subdirectories), run:

```bash
uv run python3 prepare.py {iso3}
```

This fetches the HDX GDB, detects `{ref_version}`, increments to `{version}`, converts all
layers to GeoParquet (GEOPARQUET_VERSION BOTH, ZSTD-15), and outputs:
- `{iso3}/{ref_version}/` — reference layers from HDX
- `{iso3}/{version}/` — input layers from `{iso3}/raw/`

Input files are named `{iso3}_{source_stem}.parquet`. After confirming the admin level
mapping, rename them to `{iso3}_admin{N}.parquet`.

### 3. Check for existing progress

```bash
cat {iso3}/{version}/REPORT.md 2>/dev/null || echo "No report yet"
find {iso3}/{version}/ -type f | sort
```

If `REPORT.md` exists, read it to understand decisions already made and skip re-confirming
completed verification gates. Build a per-level status table — mark ✓ if files exist, – if not:

| Level | 00-compare | 01-topology | 02-schema | 03-codes | 04-attributes |
| --- | --- | --- | --- | --- | --- |
| admin3 | ✓/– | ✓/– | ✓/– | ✓/– | ✓/– |
| admin4 | ✓/– | ✓/– | ✓/– | ✓/– | ✓/– |
| admin2 | derived | derived | ✓/– | ✓/– | ✓/– |
| admin1 | derived | derived | ✓/– | ✓/– | ✓/– |
| admin0 | derived | derived | ✓/– | ✓/– | ✓/– |

### 4. Inspect input GeoParquet

For each file in `{iso3}/{version}/`:

```bash
duckdb -c "INSTALL spatial; LOAD spatial;
  SELECT COUNT(*) AS features FROM '{iso3}/{version}/{iso3}_{stem}.parquet';
  DESCRIBE SELECT * FROM '{iso3}/{version}/{iso3}_{stem}.parquet';"
```

Report: file names, feature counts, column names, sample p-codes.

### 5. Confirm and propose

Confirm the admin level mapping and ISO2/ISO3 codes with the user, rename input GeoParquet
files accordingly, then propose the next step.

---

## Directory Structure

```text
{iso3}/
  raw/                      # Immutable — raw files from source authority
  {ref_version}/            # Reference GeoParquet from HDX (e.g. v02/)
    {iso3}_admin0.parquet
    {iso3}_admin1.parquet
    {iso3}_admin2.parquet
    {iso3}_admin3.parquet
    {iso3}_neighborhoods.parquet   # or other reference-specific layers
  {version}/                # New release (e.g. v03/)
    {iso3}_admin3.parquet   # Input GeoParquet (renamed after level mapping confirmed)
    {iso3}_admin4.parquet
    00-compare/             # Changelog outputs ({iso3}_admin{N}/ per level)
    01-topology/            # Topology Cleaner outputs ({iso3}_admin{N}.geojson)
    02-schema/              # Schema-mapped, column-reordered ({iso3}_admin{N}.gpkg)
    03-codes/               # P-codes assigned and validated ({iso3}_admin{N}.gpkg)
    04-attributes/          # All attributes complete ({iso3}_admin{N}.gpkg)
    output/                 # Final COD-AB package
    REPORT.md               # Running log of decisions + shareable release summary
```

---

## Geometry Model

**Admin3 is the authoritative geometry** (for Syria; identify the base level for other countries).
Admin0/1/2 are **derived** from admin3 by dissolving — they skip topo-tools entirely.
Admin4 is a special case: it may have partial coverage and unclean topology, and may be a new
dataset replacing a differently-named reference layer (e.g., `syr_neighborhoods`). Confirm the
reference layer name to use for Stage 0 comparison at session start.

### Deriving admin0/1/2 (DuckDB)

```sql
-- Example: derive admin2 from admin3
CREATE TABLE admin2 AS
SELECT ST_Union(geom) AS geom,
       adm2_name, adm2_pcode,
       adm1_name, adm1_pcode,
       adm0_name, adm0_pcode,
       valid_on, valid_to, version, lang, lang1, lang2, lang3
FROM admin3
GROUP BY adm2_name, adm2_pcode, adm1_name, adm1_pcode,
         adm0_name, adm0_pcode, valid_on, valid_to, version, lang, lang1, lang2, lang3;
```

### Admin4 (three-step process)

1. **Topology Cleaner** — upload admin4 to [tools.fieldmaps.io](https://tools.fieldmaps.io/),
   clean internal topology, download to `{iso3}/{version}/01-topology/{iso3}_admin4.geojson`

1. **Edge Extender** — upload cleaned admin4 + final admin3, extend admin4 boundaries to
   fill admin3 coverage gaps, download result

1. **Clip to admin3** with DuckDB:

   ```sql
   SELECT a4.*, ST_Intersection(a4.geom, a3.geom) AS geom_clipped
   FROM admin4 a4
   JOIN admin3 a3 ON ST_Intersects(a4.geom, a3.geom);
   ```

---

## REPORT.md

`{iso3}/{version}/REPORT.md` serves two purposes: it is the resumability record (decisions
made, gates approved) and the shareable release summary. Claude writes to it after each
verification gate and finalizes it in Stage 6.

### Template

```markdown
# COD-AB Processing Report — {Country} ({ISO3}) {version}

**Source authority:** {name}
**Processing date:** {date}
**Previous release:** {reference layer names and feature counts}

## Input Data
| Level | File | Features |
| --- | --- | --- |

## Admin Level Mapping
| COD-AB level | Source | Geometry |
| --- | --- | --- |

ISO2: {iso2} / ISO3: {iso3}

## Stage 0 — Comparison
| Level | Reference | Input | Unchanged | Modified | New | Removed |
| --- | --- | --- | --- | --- | --- | --- |

P-code inheritance plan: {description}

## Stage 2 — Column Mapping ✓ approved {date}
| Source column | COD-AB column | Notes |
| --- | --- | --- |

Languages: lang={code}, lang1={code}, ...

## Stage 3 — P-codes ✓ approved {date}
| Level | Inherited | Generated |
| --- | --- | --- |

## Stage 4 — Attribute Flags ✓ approved {date}
{Summary of name changes reviewed and any flags accepted}

## Stage 5 — Validation
| Check | admin0 | admin1 | admin2 | admin3 | admin4 |
| --- | --- | --- | --- | --- | --- |

Accepted warnings: {list with justification, or "none"}

## Output Summary
| Level | Features | Notes |
| --- | --- | --- |

valid_on: {date} / valid_to: null / version: {version}

## Known Caveats
{Any accepted deviations from spec, data quality notes, etc.}
```

---

## COD-AB Schema

### Column order per admin level N

```text
adm{N}_name, adm{N}_name1, adm{N}_name2, adm{N}_name3, adm{N}_pcode
adm{N-1}_name, adm{N-1}_name1, adm{N-1}_name2, adm{N-1}_name3, adm{N-1}_pcode
... (repeat for each ancestor down to 0)
adm0_name, adm0_name1, adm0_name2, adm0_name3, adm0_pcode
valid_on, valid_to, area_sqkm, version, lang, lang1, lang2, lang3, center_lat, center_lon
```

Admin0 additionally has `iso2`, `iso3` before `valid_on`.

### Key rules

- **P-codes**: `{ISO2}{numeric only}`, stored as string, no delimiters, max 20 chars. Child
  pcode must start with parent pcode (hierarchically nested). Example: parent `SY02`, child `SY0201`.

- **Geometry**: EPSG:4326 only, Polygon/MultiPolygon, no Z coordinates. No overlaps or gaps
  within a level. Child polygons fully contained in one parent.

- **Names**: No leading/trailing whitespace. No ALL CAPS. No all-lowercase. Language-appropriate
  title casing. Function words/particles lowercase when interior (`al-`, `de`, `van`, etc.). No
  two siblings share the same name. Name values identical across all levels where a unit appears.

- **Dates**: `valid_on` non-null, identical for all rows; `valid_to` null for current release.

- **Version**: `v{NN}` or `v{NN}.{NN}` (e.g., `v03`, `v02.01`); identical for all rows.

- **Computed fields**: `area_sqkm` via EPSG:6933 equal-area projection; `center_lat`/`center_lon`
  via `ST_PointOnSurface()` (guaranteed inside polygon).

- **Language**: `lang` = BCP 47 code for primary name (must be romanized); `lang1`–`lang3` for
  alternate names.

- Full spec: `/Users/computer/GitHub/OCHA-DAP/hdx-cod-ab-spec/specs/boundaries/`

---

## Workflow

### Stage 0 — Compare (`{iso3}/{version}/00-compare/`)

Applies to admin3 + admin4 (derived levels have no direct source to compare).
For admin4, use the corresponding reference layer even if it has a different name (e.g.,
`syr_neighborhoods` instead of `syr_admin4`). Note in the report that it is a replacement
dataset, not a like-for-like comparison.

1. Open [tools.fieldmaps.io](https://tools.fieldmaps.io/) → **Changelog**

1. For each level: upload the reference GeoParquet (from `{iso3}/{ref_version}/`) and the
   corresponding input GeoParquet (from `{iso3}/{version}/`) side by side

1. Download crosswalk CSV + overlay GeoJSON to `{iso3}/{version}/00-compare/{iso3}_admin{N}/`

1. Read crosswalk with DuckDB:

   ```bash
   duckdb -c "SELECT relationship, COUNT(*) FROM
     read_csv('{iso3}/{version}/00-compare/{iso3}_admin3/crosswalk.csv') GROUP BY 1 ORDER BY 2 DESC;"
   ```

1. Summarize: counts of unchanged / modified / new / removed per level

1. Document p-code inheritance plan: unchanged features inherit their existing input code;
   new features are flagged for assignment in Stage 3

1. **Write to REPORT.md**: Stage 0 comparison table + p-code inheritance plan

---

### Stage 1 — Topology (`{iso3}/{version}/01-topology/`)

Applies to admin3 (base level) + admin4 (special case — see Geometry Model above).
Derived levels (admin0/1/2) skip this stage.

1. Open [tools.fieldmaps.io](https://tools.fieldmaps.io/) → **Topology Cleaner**

1. Upload the admin3 GeoParquet; review the issues table (gaps, overlaps, slivers). Export the
   issues CSV if you want Claude to recommend gap-width and sliver-tolerance settings.

1. Adjust parameters, verify fixes on the map, download cleaned file to
   `{iso3}/{version}/01-topology/{iso3}_admin3.geojson`

1. Repeat for admin4 (plus Edge Extender step — see Geometry Model)

1. Claude validates with DuckDB:

   ```bash
   duckdb -c "INSTALL spatial; LOAD spatial;
     SELECT COUNT(*) FILTER (WHERE geom IS NULL) AS null_geoms,
            COUNT(*) FILTER (WHERE NOT ST_IsValid(geom)) AS invalid_geoms
     FROM ST_Read('{iso3}/{version}/01-topology/{iso3}_admin3.geojson');"
   ```

---

### Stage 2 — Schema (`{iso3}/{version}/02-schema/`)

Applies to all levels. Admin0/1/2 are derived from admin3 here.

1. Claude reads `{iso3}/{version}/01-topology/` files with DuckDB and lists all columns

1. Claude proposes a mapping: source column → COD-AB column name (or DROP)

1. **Verification gate**: confirm column mapping and BCP 47 language codes before proceeding

1. Claude derives admin0/1/2 via DuckDB dissolve of the cleaned admin3 (see Geometry Model)

1. Claude writes all levels to `{iso3}/{version}/02-schema/{iso3}_admin{N}.gpkg` with correct
   column order

1. **Write to REPORT.md**: column mapping table + approved language codes

---

### Stage 3 — Codes (`{iso3}/{version}/03-codes/`)

Applies to all levels simultaneously.

1. Claude joins schema-mapped files with crosswalk data from `00-compare/`

1. Inherited codes: unchanged features → keep existing input p-code (if spec-valid)

1. Generated codes: new features → parent pcode + zero-padded numeric suffix
   (e.g., parent `SY02` → new child `SY020101`)

1. Derived levels (admin0/1/2): codes come from the dissolve grouping key — no generation needed

1. Full validation across all levels:
   - Format matches `^[A-Z]{2}[0-9]+$`, max 20 chars
   - Child pcode starts with parent pcode
   - No duplicates within a level
   - Stored as VARCHAR, not integer

1. **Verification gate**: show count of inherited vs. generated codes per level; user confirms

1. Writes to `{iso3}/{version}/03-codes/`

1. **Write to REPORT.md**: p-code counts table

---

### Stage 4 — Attributes (`{iso3}/{version}/04-attributes/`)

Applies to all levels simultaneously.

1. Name normalization: trim whitespace; flag ALL CAPS and all-lowercase names for review;
   check cross-level consistency (same unit name everywhere it appears)

1. Compute `area_sqkm`:

   ```sql
   SELECT adm3_pcode,
          ST_Area(ST_Transform(geom, 'EPSG:4326', 'EPSG:6933')) / 1e6 AS area_sqkm
   FROM admin3;
   ```

1. Compute `center_lat`, `center_lon`:

   ```sql
   SELECT adm3_pcode,
          ST_Y(ST_PointOnSurface(geom)) AS center_lat,
          ST_X(ST_PointOnSurface(geom)) AS center_lon
   FROM admin3;
   ```

1. Set `valid_on` (ask user for date if not in source), `valid_to = NULL`, `version` (ask user),
   `lang`/`lang1-3`, `iso2`/`iso3` (admin0 only)

1. Cross-layer ancestor consistency check: verify `adm{L}_name` and `adm{L}_pcode` values
   on each row match the corresponding parent feature across all levels

1. **Verification gate**: show summary of name changes and any unresolved flags; user confirms

1. Writes to `{iso3}/{version}/04-attributes/`

1. **Write to REPORT.md**: attribute flag summary

---

### Stage 5 — Validation

Run the full COD-AB check suite via DuckDB across all `{iso3}/{version}/04-attributes/` files.
Report a pass/fail table per check per level. Fix and re-run until all MUST rules pass.
Document any accepted warnings with justification.

Checks:

- Null/empty geometries; invalid geometry; non-EPSG:4326; non-polygon type
- Overlaps within level (`ST_Intersects` self-join)
- Gaps within level (union → interior rings)
- P-code format, nesting, uniqueness, string type
- Name whitespace, casing, sibling uniqueness, cross-level consistency
- `valid_on` non-null and row-consistent; `valid_to` null; `version` format and row-consistent
- Child polygon containment within parent (cross-layer spatial join)

**Write to REPORT.md**: validation results table + accepted warnings with justification

---

### Stage 6 — Package (`{iso3}/{version}/output/`)

1. Create `{iso3}/{version}/output/`
1. Write one GeoPackage per level with spec-correct filename: `{iso3}_admin{N}`
1. Optionally export Shapefile and GeoJSON alongside
1. **Finalize REPORT.md**: add Output Summary section (final feature counts, valid_on, version)
   and copy to `{iso3}/{version}/output/REPORT.md`

---

## LLM-Specific Tasks

These are cases where Claude's judgment adds value beyond running queries:

- **Excel cross-reference**: Read Excel files in `{iso3}/raw/` with DuckDB `read_xlsx()` to
  cross-check attributes against shapefile columns
- **Transliteration consistency**: Spot-check Arabic → English romanization for consistency across
  features and levels
- **Name ambiguity**: Flag names that appear under different spellings across levels or within a level
- **Changelog interpretation**: When a feature's relationship is "complex" or "relocated" in the
  crosswalk, advise on p-code treatment
- **Topology parameters**: Given an exported issues CSV, recommend gap-width and sliver-tolerance
  settings based on the size distribution

---

## Verification Gates — Never Skip

| Gate | When | REPORT.md section |
| --- | --- | --- |
| Admin level mapping + ISO2/ISO3 | Session start | Admin Level Mapping |
| Column mapping + language codes | Stage 2 | Stage 2 |
| P-codes inherited vs. generated (counts) | Stage 3 | Stage 3 |
| Name change summary + unresolved flags | Stage 4 | Stage 4 |
| Warnings accepted in validation | Stage 5 | Stage 5 |
