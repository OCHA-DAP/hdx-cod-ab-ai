# COD-AB Data Cleaning Workspace

This workspace processes raw administrative boundary data from a source authority into a
validated COD-AB release. The previous published version is fetched automatically from HDX
and used as a reference baseline.

## Tools

| Tool | Purpose |
| --- | --- |
| [tools.fieldmaps.io](https://tools.fieldmaps.io/) | Topology Cleaner, Edge Extender, Changelog — run in browser |
| DuckDB (spatial ext) | All data inspection, transformation, attribute work, validation |
| uv | All Python scripts (`uv run`); `uv add` for dependencies |
| HDX API | Fetch previous COD-AB release into `reference/` |

DuckDB spatial: `duckdb -c "INSTALL spatial; LOAD spatial; ..."` or use `:memory:` shell.

---

## Session Start

Run this at the start of every session.

### 1. Check or fetch reference data

If `reference/` is empty, infer the country ISO3 from `input/` filenames and fetch from HDX:

```bash
ls reference/ 2>/dev/null || echo "MISSING — need to fetch"
```

To list available resources for a country:

```bash
uv run python3 -c "
import urllib.request, json, os, sys
iso3 = sys.argv[1].lower()
url = f'https://data.humdata.org/api/3/action/package_show?id=cod-ab-{iso3}'
req = urllib.request.Request(url, headers={'Authorization': os.environ.get('HDX_API_KEY','')})
data = json.loads(urllib.request.urlopen(req).read())
resources = data['result']['resources']
for r in resources:
    print(r['name'], r['url'])
" syr
```

Download the GDB resource to `reference/`.

### 2. Inspect input/

List all files:

```bash
find input/ -type f | sort
```

For each file, query with DuckDB:

```bash
duckdb -c "INSTALL spatial; LOAD spatial;
  SELECT COUNT(*) AS features FROM ST_Read('input/path/to/file.shp');
  DESCRIBE SELECT * FROM ST_Read('input/path/to/file.shp');"
```

Report: file names, feature counts, column names, CRS, sample p-codes.

### 3. Scan work/ for progress

```bash
find work/ -type f 2>/dev/null | sort
```

Build a per-level status table — mark ✓ if files exist, – if not:

| Level | 00-compare | 01-topology | 02-schema | 03-codes | 04-attributes |
| --- | --- | --- | --- | --- | --- |
| admin3 | ✓/– | ✓/– | ✓/– | ✓/– | ✓/– |
| admin4 | ✓/– | ✓/– | ✓/– | ✓/– | ✓/– |
| admin2 | derived | derived | ✓/– | ✓/– | ✓/– |
| admin1 | derived | derived | ✓/– | ✓/– | ✓/– |
| admin0 | derived | derived | ✓/– | ✓/– | ✓/– |

### 4. Confirm and propose

Confirm the admin level mapping and ISO2/ISO3 codes with the user, then propose the next step.

---

## Directory Structure

```text
input/           # Immutable — raw files from source authority
reference/       # Previous COD-AB from HDX (auto-fetched; cached)
work/
  00-compare/    # topo-tools Changelog outputs ({iso3}_admin{N}/ per level)
  01-topology/   # topo-tools Topology Cleaner outputs ({iso3}_admin{N}.geojson)
  02-schema/     # Schema-mapped, column-reordered ({iso3}_admin{N}.gpkg)
  03-codes/      # P-codes assigned and validated ({iso3}_admin{N}.gpkg)
  04-attributes/ # All attributes complete ({iso3}_admin{N}.gpkg)
output/          # Final COD-AB package (cod_ab_{iso3}_{version}/)
```

---

## Geometry Model

**Admin3 is the authoritative geometry** (for Syria; identify the base level for other countries).
Admin0/1/2 are **derived** from admin3 by dissolving — they skip topo-tools entirely.
Admin4 (HDS for Syria) is a special case: partial coverage, unclean topology.

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

### Admin4 / HDS (three-step process)

1. **Topology Cleaner** — upload admin4 to [tools.fieldmaps.io](https://tools.fieldmaps.io/),
   clean internal topology, download to `work/01-topology/{iso3}_admin4.geojson`

1. **Edge Extender** — upload cleaned admin4 + final admin3, extend admin4 boundaries to
   fill admin3 coverage gaps, download result

1. **Clip to admin3** with DuckDB:

   ```sql
   SELECT a4.*, ST_Intersection(a4.geom, a3.geom) AS geom_clipped
   FROM admin4 a4
   JOIN admin3 a3 ON ST_Intersects(a4.geom, a3.geom);
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

### Stage 0 — Compare (`work/00-compare/`)

Applies to admin3 + admin4 (derived levels have no direct source to compare).

1. Open [tools.fieldmaps.io](https://tools.fieldmaps.io/) → **Changelog**

1. For each level: upload the reference layer (from `reference/`) and the corresponding input
   layer side by side

1. Download crosswalk CSV + overlay GeoJSON to `work/00-compare/{iso3}_admin{N}/`

1. Read crosswalk with DuckDB:

   ```bash
   duckdb -c "SELECT relationship, COUNT(*) FROM
     read_csv('work/00-compare/syr_admin3/crosswalk.csv') GROUP BY 1 ORDER BY 2 DESC;"
   ```

1. Summarize: counts of unchanged / modified / new / removed per level

1. Document p-code inheritance plan: unchanged features inherit their existing input code;
   new features are flagged for assignment in Stage 3

---

### Stage 1 — Topology (`work/01-topology/`)

Applies to admin3 (base level) + admin4 (special case — see Geometry Model above).
Derived levels (admin0/1/2) skip this stage.

1. Open [tools.fieldmaps.io](https://tools.fieldmaps.io/) → **Topology Cleaner**

1. Upload the admin3 layer; review the issues table (gaps, overlaps, slivers). Export the
   issues CSV if you want Claude to recommend gap-width and sliver-tolerance settings.

1. Adjust parameters, verify fixes on the map, download cleaned file to
   `work/01-topology/{iso3}_admin3.geojson`

1. Repeat for admin4 (plus Edge Extender step — see Geometry Model)

1. Claude validates with DuckDB:

   ```bash
   duckdb -c "INSTALL spatial; LOAD spatial;
     SELECT COUNT(*) FILTER (WHERE geom IS NULL) AS null_geoms,
            COUNT(*) FILTER (WHERE NOT ST_IsValid(geom)) AS invalid_geoms
     FROM ST_Read('work/01-topology/syr_admin3.geojson');"
   ```

---

### Stage 2 — Schema (`work/02-schema/`)

Applies to all levels. Admin0/1/2 are derived from admin3 here.

1. Claude reads `work/01-topology/` files with DuckDB and lists all columns

1. Claude proposes a mapping: source column → COD-AB column name (or DROP)

1. **Verification gate**: confirm column mapping and BCP 47 language codes before proceeding

1. Claude derives admin0/1/2 via DuckDB dissolve of the cleaned admin3 (see Geometry Model)

1. Claude writes all levels to `work/02-schema/{iso3}_admin{N}.gpkg` with correct column order

---

### Stage 3 — Codes (`work/03-codes/`)

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

1. Writes to `work/03-codes/`

---

### Stage 4 — Attributes (`work/04-attributes/`)

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

1. Writes to `work/04-attributes/`

---

### Stage 5 — Validation

Run the full COD-AB check suite via DuckDB across all `work/04-attributes/` files.
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

---

### Stage 6 — Package (`output/`)

1. Create `output/cod_ab_{iso3}_{version}/`
1. Write one GeoPackage per level with spec-correct filename: `{iso3}_admin{N}`
1. Optionally export Shapefile and GeoJSON alongside
1. Generate release notes: feature counts added / removed / modified per level vs. reference,
   summary of p-codes generated, any known caveats or accepted warnings

---

## LLM-Specific Tasks

These are cases where Claude's judgment adds value beyond running queries:

- **Excel cross-reference**: Read Excel files in `input/` with DuckDB `read_xlsx()` to cross-check
  attributes against shapefile columns
- **Transliteration consistency**: Spot-check Arabic → English romanization for consistency across
  features and levels
- **Name ambiguity**: Flag names that appear under different spellings across levels or within a level
- **Changelog interpretation**: When a feature's relationship is "complex" or "relocated" in the
  crosswalk, advise on p-code treatment
- **Topology parameters**: Given an exported issues CSV, recommend gap-width and sliver-tolerance
  settings based on the size distribution

---

## Verification Gates — Never Skip

| Gate | When |
| --- | --- |
| Admin level mapping + ISO2/ISO3 | Session start |
| Column mapping + language codes | Stage 2 |
| P-codes inherited vs. generated (counts) | Stage 3 |
| Name change summary + unresolved flags | Stage 4 |
| Warnings accepted in validation | Stage 5 |
