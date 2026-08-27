# Shared utilities for the data pipeline.
#
# This package contains only genuinely cross-cutting helpers:
#   geo.py — ArcGIS REST, atomic writes, banners, human_bytes
#
# Domain-specific helpers have moved to their subpackages:
#   wind/gwa.py — Global Wind Atlas API helpers
#   infrastructure/helpers.py — GeoJSON load/filter/stats
