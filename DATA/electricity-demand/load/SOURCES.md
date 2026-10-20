# NSW zone-substation maximum demand — sources, method and licence notes

Prepared 19 October 2026 (Australia/Sydney). Output: `nsw_zone_substation_max_demand.csv` (543 rows).

## Coverage at a glance

| DNSP | Rows | What `max_demand` is | Status |
|---|---|---|---|
| ausgrid | 177 | **Recorded** peak demand, summer 2024/25, MVA | Complete |
| essential | 366 | **POE50 forecast** peak demand, summer 2025/26, MVA. Essential publishes no recorded per-substation maximum demand | Complete, but forecast, not recorded. See caveat 1 |
| endeavour | 0 | — | **Missing.** See "Endeavour: why it is missing" |

No source gives coordinates or a town/suburb per substation, so `latitude`, `longitude` and `locality` are blank for every row.

## Download log

All files were fetched on **2026-10-19** by the Claude desktop app's built-in browser on the user's Mac. The cloud workspace's network allowlist blocked these sites. Each file was copied across byte-for-byte, and its SHA-256 matched the hash the browser computed on the original download. Files are stored unmodified under `raw/`.

| Saved file | Download URL | Bytes | SHA-256 |
|---|---|---|---|
| `raw/essential/DAPR 2025 BSP, ZS and Lines Extract Summary - V2.xlsx` | https://dapr.essentialenergy.com.au/DAPR%202025%20BSP,%20ZS%20and%20Lines%20Extract%20Summary%20-%20V2.xlsx | 225,487 | eefd0606de5936cea772c3df696360126d401f667605072517cb3d4fbcc225b5 |
| `raw/essential/DAPR 2025 Limitations Annual Data Essential Energy.xlsx` | https://dapr.essentialenergy.com.au/essential_data/DAPR%202025%20Limitations%20Annual%20Data%20Essential%20Energy.xlsx | 625,965 | 0577b3e030b6b32bad464bc8953d045d62129bc3d0711242ab1d44610bc51bd6 |
| `raw/essential/DAPR_Essential_Energy_2025.pdf` | https://dapr.essentialenergy.com.au/DAPR_Essential_Energy_2025.pdf | 3,168,057 | 46046845a4f1aaf058df064a7d17d7c94c1cec498f03b5c0a16b22cb7f03bad1 |
| `raw/ausgrid/Ausgrid_Substation_Capacity_and_Demand_Forecast_2025.xlsx` (served without a filename; named here) | https://aopt-p-001.sitecorecontenthub.cloud/api/public/content/2f1a73b7329b4496bac54d39bbc02e9c?v=ecf15b51 (linked as "Substation Capacity and Demand Forecast" from https://www.ausgrid.com.au/about-us/regulation-and-compliance/network-planning/dtapr) | 105,538 | f9f1d537fa3d39e0223c3fb99408be7d9605d7e04ca6306292f18e0895a8fbda |
| `raw/endeavour/DAPR 2025.pdf` | https://dapr.endeavourenergy.com.au/endeavour_data/DAPR%202025.pdf | 2,469,600 | 2a958edda1c244f9d48784a00a20fc54e0edd12de946b69e57e71e072162b717 |

**Opened in the browser for inspection but not saved.** None of these supplied rows to the CSV.
- Ausgrid DTAPR 2025 full report PDF, 26,275,716 bytes: https://aopt-p-001.sitecorecontenthub.cloud/api/public/content/00bf63b95a574b5884bab499b9ae6738?v=fd7159e6. I used it only for the column definitions on PDF page 41 (printed pp. 80–81), which define "Actual Load (MVA)" as recorded peak demand. It is too large for the transfer channel available in this session. Download it from the URL if you want a local copy.
- Ausgrid DTAPR System Limitation Template FY25 (.xlsx, 47,628 bytes, SHA-256 b3316e1f…5935): https://dtapr.ausgrid.com.au/ausgrid_data/DTAPR%20System%20Limitation%20Template%20FY25.xlsx. It covers only about 20 constrained assets.
- Ausgrid Feeder Forecast (.xls, 407,552 bytes): https://aopt-p-001.sitecorecontenthub.cloud/api/public/content/bc7204761acf46139a99308926ef36ca?v=d3d782f4. It covers sub-transmission feeders, not zone substations.

## Extraction method

- **Ausgrid.** Sheet `Actual Demand (ZS)`, column G ("Summer" → "2024/25 (MVA)"). There is one row per named zone substation, rows 7–183. The workbook also has an `Actual Demand (STS)` sheet for subtransmission substations, which is excluded because it is not zone substations. Winter 2024 actuals (column M) and earlier years are in the same sheet if you want them.
- **Essential.** Sheet `ZSSummer`, column L ("Forecast (MVA)" → "25/26"), rows 3–368. The DAPR PDF (page 17) states that all published forecasts are POE50. A matching `ZSWinter` sheet has the 2026 winter forecasts.
- Values were read with openpyxl exactly as stored in the cells. No rounding, conversion or gap-filling was done. No source cell was empty or non-numeric, so no `max_demand` is blank.
- `source_page` gives the sheet, row and column of each figure.
- The Essential portal's map data files (`serve.php?file=…csv`, e.g. `dapr_spatial_mapping.csv`) are encrypted. I did not try to decode them. They are the likely home of substation coordinates.

## Caveats and flagged rows

1. **Essential figures are forecasts, not recorded demand.** Each row says so in `data_year`. The DAPR PDF gives recorded maximum demand only for the network as a whole (Figure 3). Recorded per-substation load traces are on a separate page, https://www.essentialenergy.com.au/our-network/network-projects/zone-substation-reports. Those were not used, because taking the peak from a trace is a derived number, not a transcription. Mixing these rows with Ausgrid's recorded actuals in a scoring model compares like with unlike, so decide whether to keep them.
2. **Season choice.** Both DNSPs publish summer and winter figures. Summer was used throughout. Some substations peak in winter, so their summer figure is not their annual maximum.
3. **Essential `ZSSummer` includes some sub-transmission substations.** Examples are `Terranora 110/66kV` at 97.37 MVA and `Yanco 33/11kV`. Some sites are also split by voltage, such as `Cudgen 11kV` and `Cudgen 33kV`. All are kept as printed. Filter them out if you need zone substations only.
4. **`Pindari` (essential) = 0** as printed in the source.

## 10-row verification

The 10 rows were chosen by `random.sample` with seed 20261019. Each was re-checked against the **live** source file in the browser, using a second spreadsheet reader (SheetJS) and lookup by substation name rather than row number. **All 10 match. None are uncertain.**

| dnsp | substation | CSV value | Source value | Source location |
|---|---|---|---|---|
| essential | Moama | 14.68 | 14.68 | ZSSummer r333 L |
| essential | Wenna | 2.86 | 2.86 | ZSSummer r126 L |
| essential | Moruya Town | 5.63 | 5.63 | ZSSummer r220 L |
| ausgrid | OLYMPIC PARK | 30.52 | 30.52 | Actual Demand (ZS) r122 G |
| essential | Coolamon | 5.06 | 5.06 | ZSSummer r302 L |
| essential | Woodlawn | 5.59 | 5.59 | ZSSummer r276 L |
| essential | Rappville | 0.55 | 0.55 | ZSSummer r31 L |
| essential | Yanco 33/11kV | 2.71 | 2.71 | ZSSummer r360 L (row is sub-transmission; see caveat 3) |
| essential | Kootingal | 6.68 | 6.68 | ZSSummer r144 L |
| essential | Terranora 110/66kV | 97.37 | 97.37 | ZSSummer r8 L (row is sub-transmission; see caveat 3) |

Extra checks: `Pindari` = 0 confirmed the same way. Every column header used was asserted in code before extraction ("Forecast (MVA)"/"25/26"; "Summer"/"2024/25 (MVA)").

## Endeavour: why it is missing

The Endeavour DAPR 2025 PDF (sections 6.0 and 6.5, PDF pp. 33 and 40) says the zone-substation capacity and demand forecasts are published **only** in the DAPR Mapping Portal. The portal's exportable tables, with Copy/CSV/Excel buttons, are the DAPR Template (RIT-D projects), Feeder Overload and Historic Load Trace. **None of them is a zone-substation demand table.** Substation figures appear only in individual map pop-ups. A link to a substation spreadsheet was not found on endeavourenergy.com.au either. Following the brief, no approximate numbers were produced. To get the data, ask Endeavour (see licence notes) or decide whether a pop-up-by-pop-up transcription is acceptable.

## Coordinates: OpenStreetMap (ODbL) — separate from the demand magnitudes

The 543 rows carry demand **magnitudes** but no coordinates. Coordinates are
added separately by `pipeline.demand.geocode_load` from two point layers:
Geoscience Australia (primary, already in-repo, open) and **OpenStreetMap
(second)**. OSM supplies the urban distribution zone substations the GA
transmission layer lacks.

- **OSM acquisition.** `scripts/_acquire_osm_substations_nsw.py` makes one
  read-only Overpass POST for named `power=substation` nodes/ways inside the NSW
  admin area, drops `substation=traction`/`rail`, and writes
  `DATA/infrastructure/substations/osm_substations_nsw.geojson` (EPSG:4326). The
  snapshot manifest (`DATA/infrastructure/metadata/download_manifest.json`)
  records the dataset, Overpass URL, the **exact query string**, retrieval time,
  feature count, bytes, SHA-256, CRS, and the licence credit below. The pipeline
  reads the frozen snapshot, never the live API.
- **Overpass query (recorded verbatim in the manifest):**
  ```
  [out:json][timeout:120];
  area["ISO3166-2"="AU-NSW"][admin_level=4]->.nsw;
  (
    node["power"="substation"]["name"](area.nsw);
    way["power"="substation"]["name"](area.nsw);
  );
  out tags center;
  ```
- **Licence.** OpenStreetMap data is **© OpenStreetMap contributors, licensed
  under the Open Database License (ODbL) 1.0**
  ([openstreetmap.org/copyright](https://www.openstreetmap.org/copyright);
  [ODbL summary](https://opendatacommons.org/licenses/odbl/summary/)). Baseline
  obligation is attribution; share-alike attaches only to a *distributed*
  derived database, not to internal use. Content was rephrased for compliance
  with licensing restrictions.
- **Provenance split — different reuse rights.** **Coordinates come from OSM
  (open, ODbL, attributed).** **Demand magnitudes come from the DNSP DAPR data
  (restricted, internal-use only — see the licence findings below).** These are
  recorded as separate provenances because they carry different redistribution
  rights: the coordinates could be redistributed under ODbL with attribution,
  whereas the demand figures are accepted here as a knowing internal-use
  decision and are **not** licensed for third-party redistribution. If a derived
  substation *database* built on the OSM coordinates were ever published, that
  database would need to be offered under ODbL.

## Licence / terms findings (reported, not decided)

None of the three DNSPs publishes the data under an open licence such as CC-BY. I'm not a lawyer, so treat the following as a summary of what each document says, not legal advice. **No terms were accepted, no data request was submitted and no email was sent.**

**Essential Energy**
- Where the text is: the `Disclaimer` sheet of the BSP/ZS/Lines workbook; DAPR PDF p. 7; the "DAPR Portal Disclaimer" pop-up at https://dapr.essentialenergy.com.au/ (in-page, no separate URL).
- What it says: the report is published under NER clauses 5.12.2 and 5.13.2 to notify Registered Participants and Interested Parties, and "should only be used for those purposes". Users must independently verify suitability. No warranty is given.
- Reuse in a third-party screening model: not granted by the published text, and the purpose limit points the other way. Written permission would be needed.
- Contact: dmcoordinator@essentialenergy.com.au; DM Coordinator, PO Box 5730, Port Macquarie NSW 2444.

**Ausgrid**
- Where the text is: the "APR Portal Disclaimer" pop-up at https://dtapr.ausgrid.com.au/ (in-page, no separate URL); site terms at https://www.ausgrid.com.au/disclaimer, linked from the DTAPR data page.
- What it says: the portal disclaimer says its documents belong to Ausgrid and gives no warranty. The site terms say Ausgrid owns or licenses the content and allow printing for personal use. Content may not be reproduced on any other website without Ausgrid's express written permission. They are silent on data or model reuse.
- Reuse in a third-party screening model: not addressed. Written permission is the route.
- Contact: the portal has **no data-request link**, contrary to what the brief assumed. The portal's contact is Ausgrid Head of Asset Management & Planning, assetinvestment@ausgrid.com.au, GPO Box 4009 Sydney NSW 2001. The site terms name no permissions contact beyond general enquiries.

**Endeavour Energy**
- Where the text is: DAPR 2025 PDF p. 2; the "DAPR Portal Disclaimer" pop-up at https://dapr.endeavourenergy.com.au/ (in-page, no separate URL).
- What it says: published under NER clause 5.13.2; "should only be used for that purpose"; intended for general information only. No warranty is given.
- Reuse in a third-party screening model: not granted. Permission would be needed. The same request would also be the practical way to get the missing substation table.
- Contact: consultation@endeavourenergy.com.au; Enterprise Portfolio Management Office, GPO Box 811 Seven Hills NSW 1730. The Network Data Request form mentioned in the brief is **not linked from the portal**, and I did not locate it.
