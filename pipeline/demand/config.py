"""
Shared configuration for the electricity demand pipeline.

All paths, defaults, and constants live here so individual stage modules
stay free of hard-coded values.
"""

from pathlib import Path

# --- Directory layout ---
PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent.parent

# Output directories (created by the pipeline if missing)
OUTPUT_DIR = PROJECT_ROOT / "DATA" / "electricity-demand"
RAW_DIR = OUTPUT_DIR / "raw"

# --- AEMO NEMWeb URLs ---
ARCHIVE_URL = "https://nemweb.com.au/Reports/Archive/Operational_Demand/ACTUAL_DAILY/"
CURRENT_URL = "https://nemweb.com.au/Reports/Current/Operational_Demand/ACTUAL_DAILY/"

# --- Default date range ---
DEFAULT_START_DATE = "2025-07-01"
DEFAULT_END_DATE = "2026-06-30"

# --- NEM regions (expected) ---
NEM_REGIONS = ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]

# --- Default regions for analysis (all 5 unless overridden) ---
DEFAULT_REGIONS = list(NEM_REGIONS)

# --- Request settings ---
TIMEOUT = 30
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5  # seconds
REQUEST_DELAY = 0.5  # polite delay between downloads

# --- Output filenames ---
def consolidated_csv_name(start_yyyymmdd: str, end_yyyymmdd: str) -> str:
    """Return the filename for the consolidated half-hourly CSV."""
    return f"aemo_operational_demand_{start_yyyymmdd}_{end_yyyymmdd}.csv"


AGGREGATED_CSV_NAME = "demand_annual_summary.csv"
AGGREGATED_META_NAME = "demand_annual_summary.meta.json"
INSPECTION_SUMMARY_NAME = "inspection_summary.txt"

# --- Demand feature layer (S1-04) ---
GRID_PATH = PROJECT_ROOT / "DATA" / "grid" / "nsw_analysis_grid.gpkg"
NEM_REGIONS_PATH = PROJECT_ROOT / "DATA" / "geographic" / "derived" / "nem_regions_asgs2021_national.geojson"
# ABS UCL 2021 (NSW) urban-centre/locality polygons used as the spatial weight
# for urban-footprint demand allocation (same extract the geographic feature
# stage uses for urban_area).
URBAN_WEIGHTS_PATH = PROJECT_ROOT / "DATA" / "geographic" / "urban" / "abs_ucl_2021_nsw.geojson"
# Geoscience Australia NSW substation point layer, used by
# pipeline.demand.geocode_load to give the name-only DNSP load rows coordinates.
GA_SUBSTATIONS_PATH = PROJECT_ROOT / "DATA" / "infrastructure" / "substations" / "ga_substations_2026_nsw.geojson"
# OpenStreetMap named power=substation points for NSW (ODbL, built by
# scripts/_acquire_osm_substations_nsw.py). Used by pipeline.demand.geocode_load
# as the SECOND coordinate source for load rows the GA transmission layer lacks
# (urban distribution zone substations). Licence: ODbL 1.0, (c) OpenStreetMap
# contributors; attribution required wherever these coordinates are surfaced.
OSM_SUBSTATIONS_PATH = PROJECT_ROOT / "DATA" / "infrastructure" / "substations" / "osm_substations_nsw.geojson"
# Nominatim (OSM place-geocoding) centroids for the GA+Overpass-unmatched NSW
# substations (ODbL, built by scripts/_acquire_nominatim_substations_nsw.py).
# Used by pipeline.demand.geocode_load as the THIRD coordinate source for load
# rows neither GA nor the OSM power=substation layer carries. Nominatim returns a
# SUBURB/LOCALITY CENTROID (a few km off the substation), not a precise point, so
# every match from this tier is flagged lower-confidence (coord_source='nominatim',
# nominatim_low_confidence=True) and never mixed with GA/Overpass precision. It is
# only tolerable because load_weighted uses a 15 km decay / 40 km radius. Frozen
# snapshot read at run time; the public endpoint is never hit from the pipeline.
# Licence: ODbL 1.0, (c) OpenStreetMap contributors; attribution required wherever
# these coordinates are surfaced.
NOMINATIM_SUBSTATIONS_PATH = PROJECT_ROOT / "DATA" / "infrastructure" / "substations" / "nominatim_substations_nsw.geojson"
# Geocoded real zone-substation load points (built by geocode_load from the NSW
# DNSP DAPR max-demand extract). Stored EPSG:4326; carries `max_demand` (MVA).
LOAD_WEIGHTS_PATH = PROJECT_ROOT / "DATA" / "electricity-demand" / "load" / "nsw_zone_substation_load_points.gpkg"
LOAD_POINTS_LAYER = "load_points"
# The load metric column (maximum demand, MVA) in both the raw CSV and the
# geocoded layer. Used directly as a relative-shape weight; no MVA->MW
# conversion is done (the per-region rescale absorbs units — see feature.py).
LOAD_MVA_COLUMN = "max_demand"
FEATURE_TABLE_NAME = "aemo_demand-proxy_2026_nsw.gpkg"
FEATURE_TABLE_LAYER = "demand_proxy"
METHOD_REPORT_NAME = "demand_feature_method.md"
FEATURE_MANIFEST_NAME = "download_manifest.json"
# Sidecar CSV carrying the per-cell demand coordinate-confidence tier
# (`cell_id,demand_coord_confidence`). It is written ALONGSIDE the feature
# GeoPackage so the gpkg schema — and therefore its bytes — never changes, yet
# the integration stage can join the informational tier onto the integrated
# table. Deterministic (sorted by cell_id); see
# DEMAND_COORD_CONFIDENCE_COLUMN for the tier definition.
COORD_CONFIDENCE_SIDECAR_NAME = "aemo_demand-coord-confidence_2026_nsw.csv"
STORAGE_CRS = "EPSG:4326"
COMPUTATION_CRS = "EPSG:3577"
# Allocation methods: "uniform" (legacy equal-share), "urban_weighted" (ABS UCL
# urban-footprint weighting) and "load_weighted" (real NSW zone-substation
# max-demand distance-decay). load_weighted is the default: it is the real-data
# surface (geocoded NSW DNSP DAPR zone-substation max demand across all three
# DNSPs) and it removes the degenerate urban-max normalisation artefact that
# urban_weighted injected into the top-100 (44 out-of-state QLD1 non-REZ cells).
# uniform and urban_weighted remain selectable via --allocation-method.
DEFAULT_ALLOCATION_METHOD = "load_weighted"
ALLOCATION_METHODS = ("uniform", "urban_weighted", "load_weighted")
CONFIDENCE_LEVELS = ("high", "medium", "low")

# --- Demand coordinate-confidence transparency tier (surface-only metadata) ---
# A per-cell, INFORMATIONAL tier that records whether a cell's load_weighted
# demand signal rode a low-confidence geocoded substation (a Nominatim
# suburb/locality CENTROID or an OSM low-confidence match). It is metadata: it
# never feeds back into demand_proxy, the composite score, the criteria weights
# or the ranking — it only lets an analyst audit a cell's demand provenance.
#
# Definition (conservative, matching the distance-decay aggregation in
# compute_load_cell_weights):
#   - "low"  : at least one low-confidence load point (nominatim_low_confidence
#              OR osm_low_confidence) lies within LOAD_SEARCH_RADIUS_M of the
#              cell centroid — i.e. it CONTRIBUTES to that cell's load weight.
#   - "high" : an assigned cell whose contributing load points (within the
#              search radius) are all precise (GA / portal / OSM-high), OR a
#              cell with no load point in range (it never rode a low-confidence
#              point).
#   - "n/a"  : NOT APPLICABLE — the allocation method has no load points
#              (urban_weighted / uniform), or the cell is outside every NEM
#              region (unassigned). Under the committed urban_weighted default
#              every cell is "n/a"; the signal is wired in ahead of any later
#              flip to load_weighted.
DEMAND_COORD_CONFIDENCE_COLUMN = "demand_coord_confidence"
DEMAND_COORD_CONFIDENCE_HIGH = "high"
DEMAND_COORD_CONFIDENCE_LOW = "low"
DEMAND_COORD_CONFIDENCE_NA = "n/a"
DEMAND_COORD_CONFIDENCE_LEVELS = (
    DEMAND_COORD_CONFIDENCE_HIGH,
    DEMAND_COORD_CONFIDENCE_LOW,
    DEMAND_COORD_CONFIDENCE_NA,
)
# Columns on the geocoded load-point layer that flag a lower-confidence
# coordinate (see geocode_load). A True in EITHER marks the point low-confidence.
LOAD_LOW_CONFIDENCE_COLUMNS = ("nominatim_low_confidence", "osm_low_confidence")
DEMAND_INPUT_COLUMN = "MEAN_DEMAND_MW"
CONSERVATION_TOLERANCE_MW = 1e-6

# --- Urban-footprint weighting (ABS UCL 2021) ---
# ABS UCL "Section of State" codes to DROP before the overlap. Code "13" is
# "Rural Balance" — a single catch-all polygon covering everything outside every
# real urban centre/locality, which would swamp the weighting. Codes 10/11/12
# (Major Urban / Other Urban / Bounded Locality) are genuine urban areas, kept.
URBAN_EXCLUDE_SOS_CODES = {"13"}
# Every assigned cell receives this floor weight (in addition to any urban
# overlap area) so that no assigned cell can carry zero weight and each region's
# demand is still conserved. This is a modelling choice: cells with no urban
# overlap are allocated purely on the floor and flagged `medium`.
DEMAND_WEIGHT_FLOOR = 0.05
# Ordinal multiplier applied to the urban-overlap area per ABS UCL
# `sosr_name_2021` population band. All bands are set to 1.0 for now
# (footprint-only baseline); these are tunable later without a schema change.
SOSR_WEIGHT_MULTIPLIERS = {
    "1 million or more": 1.0,
    "250,000 to 999,999": 1.0,
    "100,000 to 249,999": 1.0,
    "50,000 to 99,999": 1.0,
    "20,000 to 49,999": 1.0,
    "10,000 to 19,999": 1.0,
    "5,000 to 9,999": 1.0,
    "4,999 or less": 1.0,
    "1,000 to 4,999": 1.0,
    "500 or more": 1.0,
    "499 or less": 1.0,
    "200 to 499": 1.0,
    "Remainder of State/Territory": 1.0,
}
# Default multiplier for any band not present in SOSR_WEIGHT_MULTIPLIERS.
SOSR_DEFAULT_MULTIPLIER = 1.0

# --- Real load weighting (NSW zone-substation max demand, "load_weighted") ---
# Each geocoded substation spreads its max-demand (MVA) over nearby cells with a
# distance-decay kernel computed in EPSG:3577 (metres):
#   w_cell = Σ_s  load_mva_s · exp(-d(cell, s) / LOAD_DECAY_LENGTH_M)
#            over substations s within LOAD_SEARCH_RADIUS_M of the cell,
#            + DEMAND_WEIGHT_FLOOR for every assigned cell.
# These are modelling choices (documented like DEMAND_WEIGHT_FLOOR). The decay
# length sets how sharply demand concentrates near real substations; the search
# radius caps how far a substation's influence reaches (cells beyond it fall
# back to the floor -> medium confidence). The per-region rescale in
# allocate_demand's weighted branch makes only the RELATIVE shape matter, so the
# MVA-vs-MW and forecast-vs-recorded mismatches never affect conservation.
# 15 km decay / 40 km cutoff concentrate demand around substations while keeping
# the ~5 km analysis grid smooth and leaving sparsely-covered areas on the floor.
LOAD_DECAY_LENGTH_M = 15_000.0
LOAD_SEARCH_RADIUS_M = 40_000.0

# NSW bounding box used by geocode_load to validate coordinates that arrive
# WITH a demand row (the Endeavour portal extract carries precise WGS84
# positions). A row whose latitude/longitude is non-empty and falls inside this
# box bypasses the GA->OSM->Nominatim name-geocoding entirely and is emitted as a
# precise point with coord_source="portal". The box matches the Nominatim
# acquisition safeguard (see load/SOURCES.md).
NSW_BBOX_LAT_MIN = -37.51
NSW_BBOX_LAT_MAX = -28.16
NSW_BBOX_LON_MIN = 141.0
NSW_BBOX_LON_MAX = 153.7

# --- Pipeline stages (in execution order) ---
STAGES = ["download", "validate", "inspect", "aggregate", "feature"]
