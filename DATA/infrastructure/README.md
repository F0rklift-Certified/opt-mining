# Electricity Infrastructure Data

**Data Snapshot Notice:** These files are raw snapshots downloaded on
2026-08-13 to 2026-08-18 from GA, AEMO, and EnergyCo. They are stored here for
reproducibility of the Task 3 investigation. For production scoring, these
should be refreshed via the source scripts.

This directory contains Task 3 source samples, derived study-area files and
metadata for transmission lines, substations, generators and renewable energy
zones.

- `transmission-lines/` — transmission line source data and samples
- `substations/` — transmission substations and connection-point samples
- `generators/` — generation facilities and wind-farm validation samples
- `renewable-energy-zones/` — REZ boundaries or reference layers
- `metadata/` — source register, licences and inspection reports

Original downloads and derived files must be distinguishable by filename. Do
not overwrite authoritative source files.

## Current status

The Geoscience Australia line, substation and major-power-station samples have
been downloaded and inspected. AEMO's public KCI connection-project file and
2026 ISP REZ GIS file are also downloaded and inspected. NSW EnergyCo GIS
boundary samples for New England, Central-West Orana and Hunter-Central Coast
are stored under `renewable-energy-zones/energyco-nsw/`.

For the screening model, use the GA layers for distances to lines and
substations. Use EnergyCo boundaries for NSW-specific REZ overlays and AEMO's
KMZ for national/ISP comparison. Treat AEMO KCI as project context; none of
these sources proves spare network capacity or a connection guarantee.
