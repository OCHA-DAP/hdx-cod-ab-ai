# COD-AB Data Cleaning Workspace

This workspace processes raw administrative boundary data from a source authority into a
validated COD-AB release. The previous published version is fetched automatically from HDX
and used as a reference baseline. Multiple countries can be in flight simultaneously — all
work is scoped by country directory (e.g. `data/syr/`, `data/gab/`).

## Tools

| Tool | Purpose |
| --- | --- |
| [tools.fieldmaps.io](https://tools.fieldmaps.io/) | Topology Cleaner, Edge Extender, Changelog — browser UI |
| [`topo-tools`](https://pypi.org/project/topo-tools/) | Same operations (`clean`, `extend`, `match`, `change`) as a scriptable Python CLI — `uv add topo-tools` / `uv run topo-tools <command> --help` |
| DuckDB (spatial ext) | All data inspection, transformation, attribute work, validation |
| uv | All Python scripts (`uv run scripts/foo.py`); `uv add` for dependencies |
| `scripts/prepare.py` | Fetches HDX reference, detects version, converts all inputs to GeoParquet |
| `scripts/m49.py` | Downloads UN M49 country names in all 6 official UN languages → `data/m49.parquet` |

DuckDB spatial: `duckdb -c "INSTALL spatial; LOAD spatial; ..."` or use `:memory:` shell.

> **Web vs CLI**: `tools.fieldmaps.io` and `topo-tools` are equivalent implementations of the same
> operations — pick whichever is more convenient for a given step (`clean` ≈ Topology Cleaner,
> `extend` ≈ Edge Extender, `change` ≈ Changelog). Note in REPORT.md which was used. `topo-tools clean`
> reports slivers but never auto-fixes them, same as the web tool's sliver handling.

> **Multi-statement queries** (CREATE TABLE chains, CTEs): use heredoc form — `duckdb :memory: << 'EOF' ... EOF` — the `-c` flag does not support them reliably.

---

## Session Start

Run this at the start of every session.

### 1. Identify the active country

```bash
ls -d data/*/
```

If multiple countries exist, ask the user which one to work on. Set `{iso3}` = the country
code (e.g. `syr`). The version numbers are derived from the data — `{ref_version}` is the
previous HDX release (e.g. `v02`), `{version}` is the new release being prepared (e.g. `v03`).

### 2. Convert inputs to GeoParquet (if not already done)

Check whether GeoParquet files exist:

```bash
ls data/{iso3}/
```

If only `raw/` is present (no versioned subdirectories), do both steps below.

#### 2a. Reference GDB (automated)

```bash
uv run scripts/prepare.py {iso3}
```

Downloads the HDX COD-AB GDB if not already present, detects `{ref_version}`, computes
`{version}`, and writes reference layers to `data/{iso3}/{ref_version}/`.

#### 2b. Raw inputs (manual — format varies)

Convert **all** files in `data/{iso3}/raw/` to GeoParquet — including admin levels that will later
be derived (e.g. admin1/2), so they are available for reference and attribute cross-checking.
Raw inputs can arrive in any spatial format; use the appropriate DuckDB command below.

For single-layer files (Shapefile, GeoJSON, etc.):

```bash
duckdb -c "INSTALL spatial; LOAD spatial;
  COPY (SELECT * EXCLUDE (geom), geom AS geometry FROM ST_Read('data/{iso3}/raw/.../{file}'))
  TO 'data/{iso3}/{version}/00-inputs/{iso3}_{stem}.parquet'
  (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 15, GEOPARQUET_VERSION 'BOTH');"
```

For multi-layer archives (GDB, GPKG) — first list layers, then convert each:

```bash
gdal vector info data/{iso3}/raw/.../{archive}
duckdb -c "INSTALL spatial; LOAD spatial;
  COPY (SELECT * EXCLUDE (geom), geom AS geometry FROM ST_Read('data/{iso3}/raw/.../{archive}', layer='{layer}'))
  TO 'data/{iso3}/{version}/00-inputs/{iso3}_{stem}_{layer}.parquet'
  (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 15, GEOPARQUET_VERSION 'BOTH');"
```

> **Note:** `ST_Read` names the geometry column `geom` by default. Always rename it to `geometry`
> using `SELECT * EXCLUDE (geom), geom AS geometry` — sources that already use `geometry` will
> fail this exclude; check the source column name first if unsure.

After confirming the admin level mapping, rename outputs to `{iso3}_admin{N}.parquet`.

### 3. Check for existing progress

```bash
cat data/{iso3}/{version}/REPORT.md 2>/dev/null || echo "No report yet"
find data/{iso3}/{version}/ -type f | sort
```

If `REPORT.md` exists, read it to understand decisions already made and skip re-confirming
completed verification gates. Build a per-level status table — mark ✓ if files exist, – if not:

| Level | 01-schema | 02-compare | 03-codes | 04-topology | 05-attributes |
| --- | --- | --- | --- | --- | --- |
| admin3 | ✓/– | ✓/– | ✓/– | ✓/– | ✓/– |
| admin4 | ✓/– | ✓/– | ✓/– | ✓/– | ✓/– |
| admin2 | ✓/– | derived | derived | derived | ✓/– |
| admin1 | ✓/– | derived | derived | derived | ✓/– |
| admin0 | derived | derived | derived | derived | ✓/– |

### 4. Inspect input GeoParquet

For each file in `data/{iso3}/{version}/00-inputs/`:

```bash
duckdb -c "INSTALL spatial; LOAD spatial;
  SELECT COUNT(*) AS features FROM 'data/{iso3}/{version}/00-inputs/{iso3}_{stem}.parquet';
  DESCRIBE SELECT * FROM 'data/{iso3}/{version}/00-inputs/{iso3}_{stem}.parquet';"
```

Report: file names, feature counts, column names, sample p-codes.

### 5. Confirm and propose

Confirm the admin level mapping and ISO2/ISO3 codes with the user, rename input GeoParquet
files accordingly, then propose the next step.

---

## Directory Structure

```text
data/
  m49.parquet               # UN M49 country names (generated by scripts/m49.py)
  {iso3}/
    raw/                      # Immutable — raw files from source authority
    {ref_version}/            # Reference GeoParquet from HDX (e.g. v02/)
      {iso3}_admin0.parquet
      {iso3}_admin1.parquet
      {iso3}_admin2.parquet
      {iso3}_admin3.parquet
      {iso3}_neighborhoods.parquet   # or other reference-specific layers
    {version}/                # New release (e.g. v03/)
      00-inputs/              # Raw inputs converted to GeoParquet ({iso3}_admin{N}.parquet)
      01-schema/              # Schema-mapped: admin3 + admin4; admin1/2 for cross-checks
      02-compare/             # Changelog outputs ({iso3}_admin{N}_change.csv per level)
      03-codes/               # Names checked + p-codes assigned — admin3 (and admin4) only
      04-topology/            # Topology Cleaner outputs ({iso3}_admin{N}.parquet, {iso3}_admin{N}_issues.parquet)
      05-attributes/          # All attributes complete ({iso3}_admin{N}.parquet)
      06-output/              # Final COD-AB package
      REPORT.md               # Running log of decisions + shareable release summary
```

---

## Geometry Model

**Admin3 is the authoritative geometry** (for Syria; identify the base level for other countries).
Admin0/1/2 are **derived** from admin3 by dissolving at Stage 5 (Attributes) — they skip all earlier stages.
Admin4 is a special case: it may have partial coverage and unclean topology, and may be a new
dataset replacing a differently-named reference layer (e.g., `syr_neighborhoods`). Confirm the
reference layer name to use for Stage 2 comparison at session start.

### Deriving admin0/1/2 (DuckDB)

```sql
-- Example: derive admin2 from admin3
CREATE TABLE admin2 AS
SELECT ST_Union_Agg(geometry) AS geometry,
       adm2_name, adm2_pcode,
       adm1_name, adm1_pcode,
       adm0_name, adm0_pcode,
       valid_on, valid_to, version, lang, lang1, lang2, lang3
FROM admin3
GROUP BY adm2_name, adm2_pcode, adm1_name, adm1_pcode,
         adm0_name, adm0_pcode, valid_on, valid_to, version, lang, lang1, lang2, lang3;
```

### Admin4 (three-step process)

1. **Topology Cleaner** — via web (upload admin4 to [tools.fieldmaps.io](https://tools.fieldmaps.io/),
   clean internal topology, download both outputs) or CLI (`uv run topo-tools clean ...`).
   Either way, land both outputs in `data/{iso3}/{version}/04-topology/`
   (cleaned → `{iso3}_admin4.parquet`, issues → `{iso3}_admin4_issues.parquet`)

1. **Edge Extender** — via web (upload cleaned admin4 + final admin3, extend admin4 boundaries
   to fill admin3 coverage gaps) or CLI (`uv run topo-tools extend ...`), either way producing
   the extended result

1. **Clip to admin3** with DuckDB:

   ```sql
   SELECT a4.*, ST_Intersection(a4.geom, a3.geom) AS geom_clipped
   FROM admin4 a4
   JOIN admin3 a3 ON ST_Intersects(a4.geom, a3.geom);
   ```

---

## REPORT.md

`data/{iso3}/{version}/REPORT.md` serves two purposes: it is the resumability record (decisions
made, gates approved) and the shareable release summary. Claude writes to it after each
verification gate and finalizes it in Stage 7.

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

## Stage 1 — Column Mapping ✓ approved {date}
| Source column | COD-AB column | Notes |
| --- | --- | --- |

Languages: lang={code}, lang1={code}, ...

## Stage 2 — Comparison
| Level | Reference | Input | Unchanged | Modified | New | Removed |
| --- | --- | --- | --- | --- | --- | --- |

P-code inheritance plan: {description}

## Stage 3 — Names & Codes ✓ approved {date}
| Level | Inherited | Generated |
| --- | --- | --- |

Name/pcode flags: {summary of mismatches reviewed and any accepted}

## Stage 6 — Validation
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
  This legacy ISO2 scheme is the standard for all current-cycle releases (e.g. AGO, BDI, SYR).

- **Geometry**: EPSG:4326 only, Polygon/MultiPolygon, no Z coordinates. No overlaps or gaps
  within a level. Child polygons fully contained in one parent.

- **Names**: No leading/trailing whitespace. No ALL CAPS. No all-lowercase. Language-appropriate
  title casing. Function words/particles lowercase when interior (`al-`, `de`, `van`, etc.). No
  two siblings share the same name. Name values identical across all levels where a unit appears.

- **Dates**: `valid_on` non-null, identical for all rows; `valid_to` null for current release.

- **Version**: `v{NN}` or `v{NN}.{NN}` (e.g., `v03`, `v02.01`); identical for all rows.

- **Computed fields**: `area_sqkm` via EPSG:6933 equal-area projection; `center_lat`/`center_lon`
  via `ST_PointOnSurface()` (guaranteed inside polygon).

- **Spatial majority joins** (assigning parent attributes): use `ST_MaximumInscribedCircle(geometry).center`
  as the representative point — it is the pole of inaccessibility (deepest interior point), safer than
  centroid (which can fall outside concave polygons) and available natively in DuckDB spatial.
  Usage: `JOIN parent ON ST_Within(ST_MaximumInscribedCircle(child.geometry).center, parent.geometry)`

- **Language**: `lang` = BCP 47 code for primary name (must be romanized); `lang1`–`lang3` for
  alternate names.

- Full spec: [`OCHA-DAP/hdx-cod-ab-spec`](https://github.com/OCHA-DAP/hdx-cod-ab-spec), `specs/boundaries/`
  — clone as a sibling of this repo if not already present locally

---

## Workflow

**Output sort order** — every GeoParquet written at any stage must be sorted consistently:
1. Parent pcode ascending (e.g. `adm3_pcode` for an admin4 file)
2. `TRY_CAST(adm{N}_code AS INTEGER) NULLS LAST` — source numeric code
3. `adm{N}_name1` — alternate-language name as tiebreaker

Apply this `ORDER BY` in every `COPY (SELECT ... ORDER BY ...) TO` statement. Consistent ordering makes diffs, comparisons, and crosswalk joins stable across runs.

### Stage 1 — Schema (`data/{iso3}/{version}/01-schema/`)

Applies to admin3 (and admin4 if present); admin1/2 get lightweight `_src` normalization only.
Admin0 is derived later in Stage 5.

1. Claude reads `data/{iso3}/{version}/00-inputs/` files with DuckDB and lists all columns

1. Claude proposes a mapping: source column → COD-AB column name (or retain as-is).
   Extra source columns that don't map to COD-AB names are kept in all intermediate files
   and dropped only at Stage 7 when writing final output — they may be useful for cross-checks.
   For `adm0_name` and alternate-language equivalents, look up the correct UN M49 short names
   from `data/m49.parquet` (run `uv run scripts/m49.py` if not present) — do not copy from
   the previous release without verifying.

1. **Verification gate**: confirm column mapping and BCP 47 language codes before proceeding

1. Claude writes schema-mapped admin3 to `data/{iso3}/{version}/01-schema/{iso3}_admin3.parquet`
   with COD-AB columns first (in spec order), then any retained source columns, then `geom`.

1. Apply the same column mapping to the raw admin1, admin2, and admin4 inputs. Write to
   `data/{iso3}/{version}/01-schema/{iso3}_admin{N}.parquet`. All source columns are retained.

1. **Geometry quality check** — run on every file written to `01-schema/`:

   **a. GeometryCollections** — fix with `ST_CollectionExtract`:
   ```bash
   duckdb -c "INSTALL spatial; LOAD spatial;
     SELECT ST_GeometryType(geometry) AS type, COUNT(*) FROM
       read_parquet('data/{iso3}/{version}/01-schema/{iso3}_admin{N}.parquet')
       GROUP BY 1 ORDER BY 2 DESC;"
   ```
   > **ST_MakeValid caveat**: `ST_MakeValid` can itself produce `GEOMETRYCOLLECTION` outputs, which break functions like `ST_MaximumInscribedCircle`. Always chain: `ST_CollectionExtract(ST_MakeValid(geometry), 3)`.

   If any `GEOMETRYCOLLECTION` rows appear, replace them in place:
   ```sql
   COPY (
     SELECT * EXCLUDE (geometry),
       CASE WHEN ST_GeometryType(geometry) NOT IN ('POLYGON','MULTIPOLYGON')
            THEN ST_CollectionExtract(geometry, 3) ELSE geometry END AS geometry
     FROM read_parquet('data/{iso3}/{version}/01-schema/{iso3}_admin{N}.parquet')
   ) TO 'data/{iso3}/{version}/01-schema/{iso3}_admin{N}.parquet'
   (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 15, GEOPARQUET_VERSION 'BOTH');
   ```

   **b. Multipart features** — for each `MULTIPOLYGON` feature, check whether its parts
   span multiple parent admin areas. If parts are all in the same parent, keep as multipart.
   If parts belong to different parents, explode to singleparts and re-attribute each via
   spatial majority join against the parent level:
   ```python
   # uv run python3 script
   import geopandas as gpd, pandas as pd
   from shapely.ops import unary_union

   admin_n = gpd.read_parquet('data/{iso3}/{version}/01-schema/{iso3}_admin{N}.parquet')
   parent  = gpd.read_parquet('data/{iso3}/{version}/00-inputs/{iso3}_admin{N-1}.parquet')
   parent_cols = ['adm{N-1}_name', 'adm{N-1}_pcode', ...]  # all ancestor cols

   is_multi = admin_n.geometry.geom_type == 'MultiPolygon'
   for _, row in admin_n[is_multi].iterrows():
       parts = list(row.geometry.geoms)
       # find majority parent for each part
       parent_pcodes = set()
       for part in parts:
           best = max(parent.itertuples(),
                      key=lambda r: part.intersection(r.geometry).area
                                    if part.intersects(r.geometry) else 0)
           parent_pcodes.add(best.adm_pcode)
       if len(parent_pcodes) == 1:
           pass  # all parts same parent — keep as multipart
       else:
           # explode and re-attribute via spatial majority join
           ...
   ```
   After any explode+re-attribute, the feature count increases; note in REPORT.md.

1. **Write to REPORT.md**: column mapping table + approved language codes

---

### Stage 2 — Compare (`data/{iso3}/{version}/02-compare/`)

Applies to admin3 + admin4 (derived levels have no direct source to compare).
For admin4, use the corresponding reference layer even if it has a different name (e.g.,
`syr_neighborhoods` instead of `syr_admin4`). Note in the report that it is a replacement
dataset, not a like-for-like comparison.

1. Via web: open [tools.fieldmaps.io](https://tools.fieldmaps.io/) → **Changelog**. Via CLI:
   `uv run topo-tools change ...` (see `--help` for arguments)

1. For each level: run the reference GeoParquet (from `data/{iso3}/{ref_version}/`) against the
   corresponding input GeoParquet (from `data/{iso3}/{version}/01-schema/`) — side by side upload
   in the web tool, or as CLI arguments

1. Produce the crosswalk CSV at `data/{iso3}/{version}/02-compare/{iso3}_admin{N}_change.csv`.
   fieldmaps.io web downloads often land at the repo root — move them before processing.

1. Read crosswalk with DuckDB:

   ```bash
   duckdb -c "SELECT relationship_class, COUNT(*) FROM
     read_csv('data/{iso3}/{version}/02-compare/{iso3}_admin3_change.csv') GROUP BY 1 ORDER BY 2 DESC;"
   ```

1. Summarize: counts of unchanged / modified / new / removed per level

1. Document p-code inheritance plan: unchanged features inherit their existing input code;
   new features are flagged for assignment in Stage 3

1. **Write to REPORT.md**: Stage 2 comparison table + p-code inheritance plan

---

### Stage 3 — Names & Codes (`data/{iso3}/{version}/03-codes/`)

Applies to admin3 (and admin4 if present). Admin0/1/2 are derived later in Stage 5.

1. Claude joins schema-mapped files (from `01-schema/`) with crosswalk data from `02-compare/`

1. Cross-check admin3's embedded adm1/adm2 name and pcode values against:
   - The current version's schema-normalized admin1/2 (`data/{iso3}/{version}/01-schema/`) —
     flags naming or pcode mismatches introduced by the new source authority
   - The previous release (`data/{iso3}/{ref_version}/`) — flags any changes vs. previous admin1/2

1. Spatial majority join: for each admin3 feature, find which source admin2 (and admin1) it
   overlaps most by area, and flag any mismatch with the embedded adm2_pcode/adm1_pcode:

   ```sql
   SELECT a3.adm3_pcode, a3.adm3_name,
          a3.adm2_pcode AS embedded_adm2,
          a2.adm2_pcode AS spatial_adm2,
          ST_Area(ST_Intersection(a3.geometry, a2.geometry)) /
            ST_Area(a3.geometry) AS overlap_frac
   FROM read_parquet('data/{iso3}/{version}/01-schema/{iso3}_admin3.parquet') a3
   JOIN read_parquet('data/{iso3}/{version}/01-schema/{iso3}_admin2.parquet') a2
     ON ST_Intersects(a3.geometry, a2.geometry)
   QUALIFY ROW_NUMBER() OVER (
     PARTITION BY a3.adm3_pcode ORDER BY overlap_frac DESC) = 1
   HAVING a3.adm2_pcode != a2.adm2_pcode;
   ```

   Mismatches are expected where new admin2 districts were carved out of old ones — verify
   each case is intentional and document in REPORT.md.

1. Name normalization: trim whitespace; flag ALL CAPS and all-lowercase names for review;
   check cross-level consistency (same unit name everywhere it appears)

1. Inherited codes: existing features → keep existing input p-code (if spec-valid); fix malformed pcodes using reference crosswalk

1. Generated codes: new features → parent pcode + zero-padded numeric suffix
   (e.g., parent `SY0200` → new admin3 child `SY020001`).
   Sort order within each parent group determines the suffix:
   1. `TRY_CAST(adm{N}_code AS INTEGER) NULLS LAST` — source numeric code ascending
   2. `adm{N}_name1` — alternate-language name as tiebreaker
   (Use `ROW_NUMBER() OVER (PARTITION BY adm{N-1}_pcode ORDER BY ...)` with `lpad(..., 2, '0')`)

   If the level has nested features (see Stage 4 below), assign circle pcodes immediately
   after their primary base polygon using a two-tier sort: `(base_rank, is_circle, circle_sub_rank)`.
   This keeps each base + its circles contiguous in the pcode sequence.

1. Full validation:
   - Format matches `^[A-Z]{2}[0-9]+$`, max 20 chars
   - Child pcode starts with parent pcode
   - No duplicates within a level
   - Stored as VARCHAR, not integer

1. Export a review CSV to `data/{iso3}/{version}/03-codes/{iso3}_admin3_review.csv` with columns:
   `pcode_old`, `pcode_new`, `change_type`, `adm3_name`, `adm3_name1`, `adm2_pcode`, `adm2_name`, `adm1_pcode`, `adm1_name`.
   Use these `change_type` values:
   - `inherited` — pcode unchanged
   - `generated_split` — No_Pcode new sub-district split from an existing one
   - `generated_created` — brand new feature with no reference equivalent
   - `updated_adm2_moved` — feature moved to a new admin2 district; pcode regenerated for nesting
   - `fixed_malformed` — pcode in source was malformed (e.g. "01" instead of "SY010000")
   - `fixed_wrong_adm2` — source embedded wrong admin2 pcode (detected via spatial join); pcode updated

1. **Verification gate**: show count by `change_type` and name/pcode mismatch flags; user reviews CSV and confirms

1. Writes GeoParquet to `data/{iso3}/{version}/03-codes/`

1. **Write to REPORT.md**: p-code counts table + name/pcode flag summary

---

### Stage 4 — Topology (`data/{iso3}/{version}/04-topology/`)

Applies to admin3 (base level) + admin4 (special case — see Geometry Model above).
Derived levels (admin0/1/2) skip this stage.

1. Via web: open [tools.fieldmaps.io](https://tools.fieldmaps.io/) → **Topology Cleaner**. Via
   CLI: `uv run topo-tools clean data/{iso3}/{version}/03-codes/{iso3}_admin3.parquet ...`

1. Review the issues table/output (gaps, overlaps, slivers). Export or inspect the issues CSV if
   you want Claude to recommend gap-width and sliver-tolerance settings. Note: `topo-tools clean`
   reports slivers but never auto-fixes them, by design — same as the web tool.

1. Adjust parameters, verify fixes (on the map for web, or by re-inspecting the output for CLI),
   land both outputs in `data/{iso3}/{version}/04-topology/`:
   - cleaned output → rename to `{iso3}_admin3.parquet`
   - issues output → keep as `{iso3}_admin3_issues.parquet` (documents what was fixed)

   fieldmaps.io web downloads often land at the repo root — move them before processing.

1. Repeat for admin4 (plus Edge Extender step — see Geometry Model)

1. Claude validates with DuckDB:

   ```bash
   duckdb -c "INSTALL spatial; LOAD spatial;
     SELECT COUNT(*) FILTER (WHERE geometry IS NULL) AS null_geoms,
            COUNT(*) FILTER (WHERE NOT ST_IsValid(geometry)) AS invalid_geoms,
            COUNT(*) FILTER (WHERE ST_GeometryType(geometry) NOT IN ('POLYGON','MULTIPOLYGON')) AS wrong_type
     FROM read_parquet('data/{iso3}/{version}/04-topology/{iso3}_admin3.parquet');"
   ```

---

### Stage 5 — Attributes (`data/{iso3}/{version}/05-attributes/`)

Applies to all levels simultaneously. Admin0/1/2 are dissolved from admin3 here for the
first and only time (see Geometry Model).

1. Derive admin0/1/2 via DuckDB dissolve of the final admin3 from `04-topology/` (or `03-codes/` if topology not yet run)

1. Compute `area_sqkm`:

   ```sql
   SELECT adm3_pcode,
          ST_Area(ST_Transform(geometry, 'EPSG:4326', 'EPSG:6933')) / 1e6 AS area_sqkm
   FROM admin3;
   ```

1. Compute `center_lat`, `center_lon`:

   ```sql
   SELECT adm3_pcode,
          ST_Y(ST_PointOnSurface(geometry)) AS center_lat,
          ST_X(ST_PointOnSurface(geometry)) AS center_lon
   FROM admin3;
   ```

1. Set `valid_on` (ask user for date if not in source), `valid_to = NULL`, `version` (ask user),
   `lang`/`lang1-3`, `iso2`/`iso3` (admin0 only)

1. Cross-layer ancestor consistency check: verify `adm{L}_name` and `adm{L}_pcode` values
   on each row match the corresponding parent feature across all levels

1. Writes to `data/{iso3}/{version}/05-attributes/`

1. **Write to REPORT.md**: output metadata (valid_on, version, feature counts per level)

---

### Stage 6 — Validation

Run the full COD-AB check suite via DuckDB across all `data/{iso3}/{version}/05-attributes/` files.
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

### Stage 7 — Package (`data/{iso3}/{version}/06-output/`)

1. Create `data/{iso3}/{version}/06-output/`
1. Write one GeoParquet per level with spec-correct filename: `{iso3}_admin{N}.parquet`.
   Drop all retained source columns — output must contain only COD-AB spec columns.
1. Export a zipped GeoDatabase: convert all levels into a single `{iso3}_{version}.gdb`,
   then zip it to `{iso3}_{version}.gdb.zip` and delete the unzipped folder:
   ```bash
   for level in admin0 admin1 admin2 admin3; do
     gdal vector convert \
       "data/{iso3}/{version}/06-output/{iso3}_${level}.parquet" \
       "data/{iso3}/{version}/06-output/{iso3}_{version}.gdb" \
       --layer "{iso3}_${level}" --append --of OpenFileGDB
   done
   cd data/{iso3}/{version}/06-output && zip -r {iso3}_{version}.gdb.zip {iso3}_{version}.gdb && rm -rf {iso3}_{version}.gdb
   ```
1. **Finalize REPORT.md**: add Output Summary section (final feature counts, valid_on, version)
   and copy to `data/{iso3}/{version}/06-output/REPORT.md`

---

## LLM-Specific Tasks

These are cases where Claude's judgment adds value beyond running queries:

- **Excel cross-reference**: Read Excel files in `data/{iso3}/raw/` with DuckDB `read_xlsx()` to
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
| Column mapping + language codes | Stage 1 | Stage 1 |
| P-codes inherited vs. generated + name/pcode mismatch flags | Stage 3 | Stage 3 |
| Warnings accepted in validation | Stage 6 | Stage 6 |
