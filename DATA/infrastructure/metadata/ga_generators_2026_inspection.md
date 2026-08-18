# Geoscience Australia Generators 2026 — Inspection

- Source: `https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer/1`
- Custodian: Geoscience Australia
- Attribution: © Commonwealth of Australia (Geoscience Australia) 2026
- Format: ArcGIS Feature Service downloaded as GeoJSON
- CRS: EPSG:7844 (GDA2020)
- National feature count: 430
- Wind feature count: 87
- NSW wind feature count: 16
- Valid point coordinates: 430/430
- Technology values: {'Solar Photovoltaic': 63, 'Turbine - Wind': 86, 'Turbine - Steam': 2, 'Turbine - Ccgt': 17, 'Turbine': 1, 'Turbine - Hydropower - Dam': 57, 'Turbine - Ocgt': 36, 'Turbine - Steam Subcritical': 40, 'Reciprocating Engine - Spark Ignition': 23, 'Reciprocating Engine - Compression Ignition': 5, 'Turbine - Gas': 11, 'Cogeneration': 5, 'None': 51, 'Cogeneration - Turbine - Steam Subcritical': 6, 'Cogeneration - Reciprocating Engine - Spark Ignition': 1, 'Turbine - Hydropower - Pumped Storage': 3, 'Turbine - Hydropower - Run Of River': 2, 'Turbine - Steam Super Critical': 8, 'Reciprocating Engine': 10, 'Reciprocating Engine; Turbine - Gas': 1, 'Turbine - Wind/solar Photovoltaic': 1, 'Turbine - Concentrated Solar Thermal': 1}
- Fuel values: {'Solar': 64, 'Wind': 86, 'Biomass Or Waste': 34, 'Fossil': 182, 'Water': 62, 'Wind/solar': 1, 'None': 1}
- Generator status values: {'Operational': 412, 'Under Construction': 3, 'Non-Operational': 5, 'Decommissioned': 10}
- Wind features by state: {'VIC': 31, 'QLD': 6, 'TAS': 6, 'SA': 20, 'WA': 8, 'NSW': 16}
- Missing values by field: {'attribute_source': 1, 'attribute_source_date': 0, 'created_date': 0, 'feature_description': 0, 'feature_name': 0, 'feature_source': 0, 'feature_source_date': 410, 'feature_subtype': 0, 'feature_type': 0, 'generation_capacity_mw': 21, 'globalid': 0, 'last_edited_on': 0, 'latitude': 0, 'locality': 0, 'longitude': 0, 'number_of_units': 114, 'objectid': 0, 'owner': 42, 'primary_fuel_type': 1, 'primary_fuel_type_descriptor': 215, 'spatial_confidence': 0, 'state': 0, 'status': 0, 'technology_type': 51}

## Initial assessment

The layer provides a useful public reference set for existing generation
facilities and can identify wind facilities for later validation. It includes
technology/fuel type, capacity, status and point coordinates. Point locations
may represent a facility or a generalised location, so they should validate
regional ranking rather than exact turbine siting.
