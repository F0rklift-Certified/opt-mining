# Sensitivity analysis — baseline ranking (S4-08)

- Integrated table SHA-256: `df7073bd6c0ac9c57baf1273f2dcf2da04d3baf0c697aeeaaab3cea2e60e4da5`
- Code version: `f96a66ef5d7ef797c400a89e393c8515d929e0bb`
- Eligible cells: 23,266
- Baseline rank-1 cell: `S30.586_E151.586`

Each row re-scores every eligible cell with one change and compares the
ranking with the baseline. Normalisation bounds are shared, so only the
weights differ. Overlap is the share of the baseline top-N still in the
top-N.

| Run | Spearman (all) | Kendall τ (top-100 union) | Top-20 overlap | Top-50 overlap | Rank 1 unchanged | Max shift of baseline top-20 |
| --- | --- | --- | --- | --- | --- | --- |
| wind_speed -20% | 0.996 | 0.717 | 0.900 | 0.840 | yes | 12 |
| wind_speed -10% | 0.999 | 0.847 | 0.950 | 0.920 | yes | 4 |
| wind_speed +10% | 0.999 | 0.863 | 0.950 | 0.960 | yes | 4 |
| wind_speed +20% | 0.996 | 0.732 | 0.950 | 0.860 | no | 8 |
| dist_transmission_km -20% | 0.999 | 0.969 | 0.950 | 0.980 | yes | 2 |
| dist_transmission_km -10% | 1.000 | 0.985 | 1.000 | 1.000 | yes | 2 |
| dist_transmission_km +10% | 1.000 | 0.983 | 1.000 | 1.000 | yes | 1 |
| dist_transmission_km +20% | 0.999 | 0.969 | 0.950 | 0.980 | yes | 1 |
| demand_proxy -20% | 0.996 | 0.794 | 0.900 | 0.900 | yes | 5 |
| demand_proxy -10% | 0.999 | 0.896 | 0.950 | 0.960 | yes | 4 |
| demand_proxy +10% | 0.999 | 0.891 | 0.950 | 0.960 | yes | 2 |
| demand_proxy +20% | 0.998 | 0.815 | 0.950 | 0.900 | yes | 4 |
| dist_substation_km -20% | 1.000 | 0.967 | 1.000 | 0.980 | yes | 2 |
| dist_substation_km -10% | 1.000 | 0.983 | 1.000 | 1.000 | yes | 1 |
| dist_substation_km +10% | 1.000 | 0.990 | 1.000 | 1.000 | yes | 1 |
| dist_substation_km +20% | 1.000 | 0.977 | 1.000 | 0.980 | yes | 1 |
| slope_deg -20% | 0.999 | 0.900 | 0.950 | 0.940 | no | 4 |
| slope_deg -10% | 1.000 | 0.953 | 0.950 | 0.980 | yes | 3 |
| slope_deg +10% | 1.000 | 0.945 | 0.950 | 0.960 | yes | 3 |
| slope_deg +20% | 0.999 | 0.899 | 0.950 | 0.960 | yes | 4 |
| inside_rez -20% | 1.000 | 0.921 | 1.000 | 0.960 | yes | 0 |
| inside_rez -10% | 1.000 | 0.979 | 1.000 | 1.000 | yes | 0 |
| inside_rez +10% | 1.000 | 1.000 | 1.000 | 1.000 | yes | 0 |
| inside_rez +20% | 1.000 | 1.000 | 1.000 | 1.000 | yes | 0 |
| Scenario: Wind-led | 0.905 | 0.121 | 0.500 | 0.520 | no | 97 |
| Scenario: Grid-led | 0.981 | 0.646 | 0.850 | 0.800 | no | 13 |
