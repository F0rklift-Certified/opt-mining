"""Generate offline display-only NSW outline from the committed ABS geometry."""
from pathlib import Path
import json
from shapely.geometry import shape, mapping
from pipeline.common.geo import atomic_write_json, sha256_file


def main():
    source = Path("DATA/geographic/boundaries/abs_ste_2021_national.geojson")
    features = json.loads(source.read_text())["features"]
    nsw = next(f for f in features if str(f["properties"]["state_code_2021"]) == "1")
    outline = shape(nsw["geometry"]).simplify(0.01, preserve_topology=True)
    atomic_write_json(Path("app/web/app/shell/nsw-outline.json"), {
        "geometry": mapping(outline), "crs": "EPSG:4326",
        "source": str(source), "source_sha256": sha256_file(source),
        "attribution": "ABS ASGS 2021 State/Territory boundaries, CC BY 4.0",
        "display_simplification_degrees": 0.01,
        "note": "Display-only outline; not used for eligibility, features or scoring",
    })


if __name__ == "__main__":
    main()
