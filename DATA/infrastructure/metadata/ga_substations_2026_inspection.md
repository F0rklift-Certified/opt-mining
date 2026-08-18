# Geoscience Australia Substations 2026 — Inspection

- Source: `https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer/0`
- Custodian: Geoscience Australia
- Attribution: © Commonwealth of Australia (Geoscience Australia) 2026
- Format: ArcGIS Feature Service downloaded as GeoJSON
- CRS: EPSG:7844 (GDA2020)
- National feature count: 1866
- NSW feature count: 586
- Geometry types: {'Point': 1866}
- Valid point coordinates: 1866/1866
- States: {'QLD': 444, 'NSW': 586, 'SA': 128, 'NT': 38, 'WA': 239, 'TAS': 86, 'VIC': 326, 'ACT': 19}
- Operational status values: {'Operational': 1850, 'Under Construction': 3, 'Non-Operational': 13}
- Voltage kV values: {'110': 125, '132': 637, '220': 115, '275': 106, '33': 3, '330': 97, '400': 2, '44': 1, '500': 25, '66': 706, '88': 1, 'None': 48}
- Missing values by field: {'attribute_source': 0, 'attribute_source_date': 1, 'created_date': 0, 'feature_description': 0, 'feature_name': 2, 'feature_source': 0, 'feature_source_date': 1775, 'feature_subtype': 10, 'feature_type': 0, 'globalid': 0, 'last_edited_on': 0, 'latitude': 0, 'locality': 0, 'longitude': 0, 'objectid': 0, 'spatial_confidence': 0, 'state': 0, 'status': 0, 'voltage_kv': 48}

## Fields

attribute_source, attribute_source_date, created_date, feature_description, feature_name, feature_source, feature_source_date, feature_subtype, feature_type, globalid, last_edited_on, latitude, locality, longitude, objectid, spatial_confidence, state, status, voltage_kv

## Initial assessment

This dataset is suitable for screening-level proximity to transmission
substations. It provides point coordinates, voltage, state, locality, status and
spatial-confidence fields. It is not a complete engineering connection-capacity
register: a substation's voltage does not equal spare connection capacity. The
dataset's official safety and completeness disclaimer must be retained.
