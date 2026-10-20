# SOURCES — Endeavour Energy zone-substation maximum demand

## Source
- **Portal:** Endeavour Energy DAPR Mapping Portal (Rosetta Data Portal) — https://dapr.endeavourenergy.com.au/
- **Accessed:** 21 October 2026 (Australia/Sydney)
- **Portal data vintage:** "Latest Updates: December 2025 - DAPR PDF report and associated data have been updated." (i.e. DAPR 2025)
- **Map layer:** Substations › **Zone Substations** (`Zone-Substations_Endeavour` layer). Clicking a marker opens a small map pop-up showing only the substation name, and fills the **"Report Data for <substation>"** panel below the map. All figures come from that panel.
- **Supporting document:** DAPR 2025 PDF — https://dapr.endeavourenergy.com.au/endeavour_data/DAPR%202025.pdf (§6, §6.2, §6.4, §6.5)

## Enumeration and completeness
- The Zone Substations layer holds **186 markers** (186 unique names), read from the map's own marker list. By legend marker type: 171 "Zone Substations", 14 "Zone Substations (Proposed)" and 1 "Major Development Proposed".
- I opened the Report Data panel for **all 186** markers, one at a time, by firing each marker's own click handler. For every one I checked that the panel heading "Report Data for X" matched the marker name: 186 of 186 matched, with no skips and no duplicates.
- **Expected: 186 markers. Captured into the main CSV: 166.** The other 20 show no recorded demand (listed below).
- Coordinates are each marker's position in the map state (WGS84 decimal degrees, as given to Google Maps). The panel shows no locality, so `locality` is blank throughout.

## Which field was read as `max_demand`
Each panel has a **Technical Specifications** table (voltage, transformer MVA, installed capacity N, firm rating N-1, 95% peak-load hours, embedded generation) and **four demand tables**: Forecast Max Demand (Summer), Forecast Max Demand (Winter), Forecast Min Demand (Summer) and Forecast Min Demand (Winter). Each demand table has the columns `Forecast PF | Actual (MVA): 2024, 2025 | Forecast (MVA): 2026–2030`.

**Rule used (applied to every row):** `max_demand` = the **"Actual (MVA)" 2025** value from *Forecast Max Demand (Summer)* or *Forecast Max Demand (Winter)*, whichever is higher. The season chosen is written in `data_year`, and `source_page` names the exact table and cell. 110 rows use summer and 56 use winter. The value is copied as displayed (no rounding). The unit is **MVA**, as the panel shows it, with no conversion. Ratings, capacities and min-demand values were **not** used.

- **Recorded or forecast:** **RECORDED.** Every value comes from the "Actual (MVA)" columns. DAPR 2025 §6.5 states that the "Actual (MVA)" figure "is not temperature corrected", and that forecasts are based on temperature-corrected actuals. No forecast values are in the main CSV.
- **Forecast basis, for reference only:** DAPR §6.2/§6.4 describe 10% and 50% PoE conditions. Neither the portal nor the PDF says which PoE the zone-substation forecast columns use. This does not affect the main CSV, which holds no forecasts.
- **Season and year labelling — UNRESOLVED AMBIGUITY:** The portal labels columns only "2024" and "2025". The DAPR PDF contradicts itself:
  - §6 refers to "the 2024/25 (2025) summer", so 2025 = summer 2024/25.
  - §6.5 says "The summer 2025 refers to the 2025/26 summer."

  Because the 2025 column is a recorded value published in December 2025, summer 2024/25 is the more plausible reading, but I have not resolved it. `data_year` keeps the DAPR's own label ("2025 summer" or "2025 winter"). The PDF also defines the seasons differently in two places: §6.1 uses Sep–Mar / Apr–Aug, and §6.2 uses Nov–Mar / May–Aug.
- If you would rather have one fixed season, for example summer-only, every summer and winter Actual and Forecast value is in `endeavour_zone_substation_full_panel_detail.csv`.

## Flags (in main CSV — please review)
| Substation | Issue |
|---|---|
| Westmead ZS | Each max-demand table has **2 unlabelled data rows**. Row 1 has blank Actuals and forecasts from 2027. Row 2 has the Actuals (S 26.36/26.72; W 19.35/20.28). I used Row 2. Row 1 looks like a future split or new asset, but the portal does not say so. Screenshot: `11_Westmead_ZS_two_rows_flagged.jpg`. |
| West Liverpool 11kv ZS | Winter Actual 2025 is blank. The summer value is used without a season comparison. |
| Bringelly ZS | Winter Actual 2025 is blank. The summer value is used. |
| West Parramatta ZS | Winter Actual 2025 is blank. The summer value is used. |

Other observations, not errors: some panels show odd year-to-year swings, all transcribed exactly as shown. Examples: Figtree ZS winter 2024 26.15 vs winter 2025 16.85; North Eastern Creek ZS winter 23 → 11.56; Mungerie Park ZS summer 86.65 → 59.55; Huntingwood ZS 95% peak-load hours = 40.378. Calderwood ZS shows Installed Capacity 0 and Firm Rating 0.

## No demand shown — excluded from main CSV (20)
**Max-demand tables absent from the panel (13):** Broughton Pass ZS, Visy Paper ZS, Northern Gateway ZS (these 3 are existing, not marked proposed); Maryland ZS (Proposed), Mt Gilead ZS (Proposed), North Bomaderry ZS (Proposed), Riverstone East ZS (Proposed), South Penrith ZS (Proposed), Termeil ZS (Proposed), Western Sydney Employment Lands ZS (Proposed), Austral ZS (Proposed), West Appin ZS (Proposed), Aerotropolis 132kV ZS (Proposed; Major Development marker).

**Tables present but no recorded Actual 2025 (blank or "-") (7):**
- Robertson ZS: existing; forecasts only, from 2026.
- Calderwood ZS: existing; forecasts only, from 2026.
- Catherine Park ZS (Proposed), Menangle Park ZS (Proposed), Science Park ZS (Proposed), West Dapto ZS (Proposed), Bradfield City ZS (Proposed).

No values were estimated or inferred for any of these.

## Verification
1. **Transcription integrity:** I generated both CSVs from the cell text in the rendered panels. Each file's SHA-256 was computed in the browser and again on the saved file, and both matched:
   - main CSV `553e1233fb24be42075f61b387569d11eb814a8f0995195a0d61651db62fff96`
   - detail CSV `56398b495d56396dc6d4255666e5c7547001f78cdc627bdfa4e20aa52814cb42`
2. **Random re-check against the live portal:** After a fresh page reload, I re-opened 10 randomly chosen substations (seed 20261021). For each, I re-read the panel and compared it with the CSV. **All 10 matched:**

   | Substation | CSV value (MVA) | Season |
   |---|---|---|
   | Springwood ZS | 26.39 | summer |
   | Port Kembla ZS | 16.01 | winter |
   | Maldon ZS | 20.21 | winter |
   | Blackheath ZS | 8.29 | winter |
   | Port Central ZS | 9.12 | winter |
   | St Marys ZS | 29.38 | summer |
   | Anzac Village ZS | 25.38 | summer |
   | Box Hill ZS | 20.03 | summer |
   | North Leppington ZS | 9.72 | summer |
   | Bylong ZS | 0.38 | summer |

   Screenshots of each are in `screenshots/`, plus Westmead (flagged) and the map layer and pop-up view. Uncertain items: Westmead (row choice), and the season-year labelling noted above.
3. Demand is rendered as **readable HTML table text**, not as a chart or canvas, so no values were read from pixels. The "Historic Load Trace" Highcharts chart in each panel was **not** used.

## Method note
The portal's layer file (`serve.php?file=./layers/Zone-Substations_Endeavour.geojson`) is served **encrypted**. I did not attempt to decrypt it or bypass it. All values were read from the panels the portal itself renders when each marker is clicked. No "accept" gate was clicked, no form was submitted, no email was sent, and the Telemus AI chat was not used.

## Licence / disclaimer (verbatim)
Location: "Show DAPR Portal Disclaimer" link in the left sidebar of https://dapr.endeavourenergy.com.au/ (modal popup `#showDAPRPortalDisclaimerViewer`).

> Disclaimer
>
> Endeavour Energy is registered as a Distribution Network Service Provider.
>
> This Distribution Annual Planning Report (DAPR) Portal's associated documents has been prepared and published by Endeavour Energy under clause 5.13.2 of the National Electricity Rules. Its purpose is to notify Registered Participants and Interested Parties of the results of Endeavour Energy’s distribution network annual planning review and it should only be used for that purpose.
>
> This DAPR Portal is intended for general information only. Independent verification and assessment of the information in this report for its accuracy, completeness, reliability and suitability for purposes other than for general information should be undertaken prior to it being used for such purposes.
>
> Accordingly, Endeavour Energy makes no representations or warranty as to the accuracy, reliability, completeness or suitability for any particular purpose of the information in this Portal or associated documents. Persons reading or utilising this document acknowledge that Endeavour Energy and their employees, agents and consultants shall have no liability (including liability to any person by reason of negligence or negligent misstatement) for any statements, opinions, information or matter (expressed or implied) arising out of, contained in or derived from, or for any omissions from, the information in this document, except insofar as liability under any New South Wales and Commonwealth statute cannot be excluded.
>
> By reviewing this DAPR Portal you agree to be bound by these terms & conditions.

Note: the final sentence is a browse-wrap term ("By reviewing this DAPR Portal you agree…"). There is no click-through gate, and none was accepted.

**Use basis:** The project owner has made a knowing **INTERNAL-USE** decision to use this data, consistent with the treatment of the Essential Energy and Ausgrid data. This log records the terms. It does not decide them.

## Files
- `endeavour_zone_substation_max_demand.csv` — 166 rows, project schema.
- `endeavour_zone_substation_full_panel_detail.csv` — every value from all 186 panels (technical specs; all summer and winter max-demand Actual and Forecast cells; PF), with an `in_main_csv` flag.
- `screenshots/` — 13 images.
