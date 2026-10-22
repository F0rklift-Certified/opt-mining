# Sensitivity analysis — baseline ranking (S4-08)

- Integrated table SHA-256: `df7073bd6c0ac9c57baf1273f2dcf2da04d3baf0c697aeeaaab3cea2e60e4da5`
- Code version: `15e5a13ff0ac4fb077754f0cd254694ee8016f81`
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

## Site stability (top 20)

Every cell that reaches the top 20 in any run. *Share* is the fraction of all
runs (baseline, perturbations and scenarios) that keep it in the top 20.

| Cell | Baseline rank | Share of runs in top 20 | Best rank | Worst rank |
| --- | --- | --- | --- | --- |
| `S30.586_E151.586` | 1 | 1.00 | 1 | 20 |
| `S30.636_E151.586` | 2 | 1.00 | 1 | 10 |
| `S32.436_E149.036` | 5 | 1.00 | 2 | 10 |
| `S32.486_E149.086` | 7 | 1.00 | 3 | 11 |
| `S30.436_E151.536` | 8 | 1.00 | 6 | 15 |
| `S32.436_E149.086` | 9 | 1.00 | 1 | 15 |
| `S30.186_E151.636` | 10 | 1.00 | 4 | 13 |
| `S30.286_E151.636` | 12 | 1.00 | 5 | 18 |
| `S30.586_E151.536` | 3 | 0.96 | 3 | 25 |
| `S30.536_E151.586` | 4 | 0.96 | 4 | 36 |
| `S30.586_E151.636` | 6 | 0.96 | 5 | 29 |
| `S30.636_E151.636` | 11 | 0.96 | 6 | 30 |
| `S32.486_E149.036` | 14 | 0.96 | 12 | 22 |
| `S30.636_E151.686` | 15 | 0.96 | 14 | 38 |
| `S30.486_E151.586` | 16 | 0.96 | 12 | 50 |
| `S30.686_E151.486` | 17 | 0.96 | 14 | 37 |
| `S32.386_E148.986` | 13 | 0.93 | 10 | 42 |
| `S30.286_E151.686` | 18 | 0.85 | 7 | 30 |
| `S32.436_E148.986` | 20 | 0.74 | 19 | 54 |
| `S32.336_E148.286` | 19 | 0.70 | 9 | 116 |
| `S30.236_E151.586` | 21 | 0.33 | 8 | 38 |
| `S32.386_E148.286` | 22 | 0.26 | 16 | 79 |
| `S32.386_E149.036` | 28 | 0.07 | 19 | 54 |
| `S30.686_E151.536` | 23 | 0.04 | 19 | 48 |
| `S30.786_E151.586` | 29 | 0.04 | 20 | 52 |
| `S32.286_E148.236` | 35 | 0.04 | 20 | 184 |
| `S30.236_E151.786` | 37 | 0.04 | 13 | 68 |
| `S30.836_E151.586` | 39 | 0.04 | 17 | 66 |
| `S30.236_E151.836` | 44 | 0.04 | 15 | 78 |
| `S30.086_E151.686` | 64 | 0.04 | 16 | 103 |
| `S30.086_E151.736` | 65 | 0.04 | 18 | 102 |
| `S34.586_E149.436` | 107 | 0.04 | 6 | 951 |
| `S31.186_E151.686` | 163 | 0.04 | 11 | 279 |
| `S31.136_E151.686` | 181 | 0.04 | 14 | 290 |
