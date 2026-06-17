"""Convert the HDX reference GDB to GeoParquet and detect version numbers.

Usage: uv run python3 prepare.py <iso3>

Requires the HDX reference GDB to already be present anywhere under {iso3}/.
Outputs reference layers to {iso3}/{ref_version}/ and prints the new version to use.
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

import duckdb

logging.basicConfig(format="%(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

_COPY_OPTIONS = (
    "FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 15, GEOPARQUET_VERSION 'BOTH'"
)


def get_layers(path: Path) -> list[str]:
    """Return layer names from a spatial archive (GDB, GPKG, etc.)."""
    result = subprocess.run(
        ["gdal", "vector", "info", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        line.split(":", 1)[1].strip()
        for line in result.stdout.splitlines()
        if line.startswith("Layer name:")
    ]


def detect_ref_version(
    con: duckdb.DuckDBPyConnection,
    gdb_path: Path,
    layers: list[str],
) -> str:
    """Read the version field from the first GDB layer that has one."""
    for layer in layers:
        row = con.execute(
            f"SELECT DISTINCT version FROM ST_Read('{gdb_path}', layer='{layer}') "
            f"WHERE version IS NOT NULL LIMIT 1",
        ).fetchone()
        if row:
            return row[0]
    sys.exit(f"Could not detect version from {gdb_path}")


def increment_version(version: str) -> str:
    """Increment the major version number: 'v02' → 'v03'."""
    major = int(version.lstrip("v").split(".")[0])
    return f"v{major + 1:02d}"


def convert(
    con: duckdb.DuckDBPyConnection,
    src: str,
    dst: Path,
    layer: str | None = None,
) -> None:
    """Convert a spatial file (or archive layer) to GeoParquet. Skips if dst exists."""
    if dst.exists():
        row = con.execute(f"SELECT COUNT(*) FROM '{dst}'").fetchone()
        count = row[0] if row else 0
        log.info("  skip %s (exists, %s features)", dst.name, f"{count:,}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    layer_clause = f", layer='{layer}'" if layer else ""
    sql = (
        f"COPY (SELECT * FROM ST_Read('{src}'{layer_clause})) "
        f"TO '{dst}' ({_COPY_OPTIONS})"
    )
    con.execute(sql)
    row = con.execute(f"SELECT COUNT(*) FROM '{dst}'").fetchone()
    count = row[0] if row else 0
    log.info("  %s: %s features", dst.name, f"{count:,}")


def main() -> None:
    """Convert the HDX reference GDB to GeoParquet and print version numbers."""
    parser = argparse.ArgumentParser(
        description="Convert HDX reference GDB to GeoParquet.",
    )
    parser.add_argument("iso3", help="Country ISO3 code (e.g. syr)")
    args = parser.parse_args()
    iso3 = args.iso3.lower()

    country_dir = Path(iso3)
    gdbs = [p for p in country_dir.glob("**/*.gdb") if "raw" not in p.parts]
    if not gdbs:
        sys.exit(f"No GDB found under {country_dir}/ — download from HDX first")
    gdb = gdbs[0]

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")

    layers = get_layers(gdb)
    ref_version = detect_ref_version(con, gdb, layers)
    new_version = increment_version(ref_version)
    log.info("Reference: %s  →  New: %s\n", ref_version, new_version)

    ref_out = country_dir / ref_version
    log.info("Reference → %s/", ref_out)
    for layer in layers:
        convert(con, str(gdb), ref_out / f"{layer}.parquet", layer=layer)

    log.info("\nNow convert raw inputs manually — see CLAUDE.md Session Start Step 2.")


if __name__ == "__main__":
    main()
