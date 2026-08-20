# AEMO KCI 2026 Inspection

- **File:** `../connection-points/aemo_kci_2026.xlsx`
- **Source:** AEMO Generation Information page, Key Connection Information (KCI) public file
- **Downloaded:** 2026-08-15
- **Workbook size:** approximately 408 KB
- **Worksheet:** `Q2 2026 KCI`
- **Formatted worksheet rows:** 9,560
- **Populated connection records:** 2,354
- **Unique AEMO KCI IDs:** 1,006
- **Unique connection enquiry/application IDs:** 903 non-empty IDs
- **TNSPs represented:** 8
- **Regions represented:** 6 NEM regions

## Important field findings

The workbook contains connection identifiers, TNSP, proponent, site name, text
site-location descriptions, NEM region, technology, capacity estimates and
forecast dates. The downloaded public workbook does **not** contain latitude or
longitude columns. It therefore cannot be joined directly to candidate cells
without a separately validated geocoding or network-source step.

The KCI data is a project/connection register, not a register of spare
substation capacity. Use it as contextual evidence for proposed and active
connection activity. Use the Geoscience Australia line/substation geometries
for the Task 3 distance screen, and obtain technical feasibility data from the
relevant network service provider or AEMO when a project reaches connection
enquiry/application stage.

