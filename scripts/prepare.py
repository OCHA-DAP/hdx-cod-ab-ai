"""Fetch the HDX COD-AB reference GDB and convert it to GeoParquet.

Usage: uv run python3 prepare.py <iso3>

Downloads the GDB from HDX, converts all layers to GeoParquet in {iso3}/{ref_version}/,
and prints the ref/new version numbers for the session. The GDB is deleted after conversion.

Some GDBs trigger a segfault in DuckDB 1.5.x's bundled GDAL reader. The script probes
the GDB in a subprocess first; if that fails it converts GDB → GPKG via `gdal vector convert`
as a one-time bridge, then DuckDB reads the GPKG instead. The GPKG is also deleted afterward.
"""

import argparse
import json
import logging
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

import duckdb

logging.basicConfig(format="%(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

_HDX_API = "https://data.humdata.org/api/3/action/package_show?id=cod-ab-{iso3}"
_COPY_OPTIONS = (
    "FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 15, GEOPARQUET_VERSION 'BOTH'"
)


def download_gdb(iso3: str, country_dir: Path) -> Path:
    """Download and extract the HDX COD-AB GDB. Returns the .gdb path."""
    existing = [p for p in country_dir.glob("**/*.gdb") if "raw" not in p.parts]
    if existing:
        log.info("GDB already present: %s", existing[0])
        return existing[0]

    url = _HDX_API.format(iso3=iso3)
    log.info("Querying HDX for cod-ab-%s...", iso3)
    with urllib.request.urlopen(url) as resp:
        data = json.load(resp)

    if not data.get("success"):
        sys.exit(f"HDX dataset not found: cod-ab-{iso3}")

    resources = data["result"]["resources"]
    gdb_resources = [
        r for r in resources
        if r.get("format", "").lower() == "geodatabase"
        or ".gdb" in r.get("name", "").lower()
    ]
    if not gdb_resources:
        sys.exit(f"No GDB resource found in HDX dataset cod-ab-{iso3}")

    resource = gdb_resources[0]
    download_url = resource["url"]
    zip_name = resource["name"]
    zip_path = country_dir / zip_name

    log.info("Downloading %s...", zip_name)
    urllib.request.urlretrieve(download_url, zip_path)

    log.info("Extracting...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(country_dir)
    zip_path.unlink()

    gdbs = [p for p in country_dir.glob("**/*.gdb") if "raw" not in p.parts]
    if not gdbs:
        sys.exit("Extracted zip but no .gdb found — check the HDX resource")
    return gdbs[0]


def get_layers(path: Path) -> list[str]:
    """Return layer names from a spatial archive via `gdal vector info`."""
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


def get_version(path: Path, layers: list[str]) -> str:
    """Read the version field from the first layer that has one."""
    for layer in layers:
        result = subprocess.run(
            ["gdal", "vector", "info", "--features", "--limit", "1",
             str(path), "--layer", layer],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if "version (String) =" in line:
                return line.split("=", 1)[1].strip()
    sys.exit(f"Could not detect version from {path}")


def duckdb_can_read(path: Path, layer: str) -> bool:
    """Probe whether DuckDB can read a layer without risking a segfault in this process."""
    result = subprocess.run(
        ["duckdb", "-c",
         f"INSTALL spatial; LOAD spatial; "
         f"SELECT COUNT(*) FROM ST_Read('{path}', layer='{layer}');"],
        capture_output=True,
        timeout=30,
    )
    return result.returncode == 0


def resolve_src(gdb_path: Path, layers: list[str]) -> tuple[Path, bool]:
    """Return (src_path, used_gpkg). Converts to GPKG only if DuckDB can't read the GDB."""
    if duckdb_can_read(gdb_path, layers[0]):
        return gdb_path, False
    log.info("DuckDB cannot read this GDB directly — converting to GPKG as bridge...")
    gpkg_path = gdb_path.with_suffix(".gpkg")
    subprocess.run(
        ["gdal", "vector", "convert", "-f", "GPKG", "--quiet",
         str(gdb_path), str(gpkg_path)],
        check=True,
    )
    return gpkg_path, True


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
    parser = argparse.ArgumentParser(
        description="Fetch HDX COD-AB reference GDB and convert to GeoParquet.",
    )
    parser.add_argument("iso3", help="Country ISO3 code (e.g. syr)")
    args = parser.parse_args()
    iso3 = args.iso3.lower()

    country_dir = Path(iso3)
    country_dir.mkdir(exist_ok=True)

    gdb = download_gdb(iso3, country_dir)

    # All subprocess calls before DuckDB is initialized (avoids GDAL library conflicts)
    layers = get_layers(gdb)
    ref_version = get_version(gdb, layers)
    new_version = increment_version(ref_version)
    log.info("Reference: %s  →  New: %s\n", ref_version, new_version)

    src, used_gpkg = resolve_src(gdb, layers)

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")

    ref_out = country_dir / ref_version
    log.info("Reference → %s/", ref_out)
    for layer in layers:
        convert(con, str(src), ref_out / f"{layer}.parquet", layer=layer)

    if used_gpkg:
        src.unlink()
    shutil.rmtree(gdb)
    log.info("\nCleaned up GDB%s.", " and GPKG" if used_gpkg else "")
    log.info("Now convert raw inputs — see CLAUDE.md Session Start Step 2.")


if __name__ == "__main__":
    main()
