# 5단계 1부: 자료량에 맞춰 칸을 넓히는 클러터 지도 (JIPDA-amap)

`scripts/stage5_report.py`가 만든 파일. 스히폴 평가 구간, 측정 모형 M0, [ ]는 seed 짝 차이의 95% t-구간.
JIPDA-amap만 이 단계의 새 실행(`results/stage5/eval/`)이다. JIPDA·JIPDA-est(lam1000)는 3단계, JIPDA-est(lam200·lam5)와 JIPDA-map은 4단계 파일이다. 실행 시간은 다른 세션과 CPU를 나눈 값이다.

선택(조정 구간, seed 20271106–20271110, 점수 = 두 조건 GOSPA/JIPDA GOSPA 중 큰 값, 최소): **n20_30**

| 후보 | 점수 | map GOSPA 비 | uniform GOSPA 비 | map GOSPA (m) | uniform GOSPA (m) | map 가짜 항적 | uniform 가짜 항적 | map 시간 (s) | uniform 시간 (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| n20_30 | 1.006 | 1.001 | 1.006 | 3666 | 3009 | 2.29 | 1.05 | 38 | 12 |
| n20_100 | 1.022 | 1.003 | 1.022 | 3671 | 3058 | 2.31 | 1.08 | 39 | 12 |
| n5_30 | 1.023 | 1.009 | 1.023 | 3693 | 3061 | 2.27 | 1.00 | 36 | 17 |
| n5_100 | 1.034 | 1.025 | 1.034 | 3751 | 3094 | 2.46 | 1.03 | 45 | 13 |
| (기준) jipda map | | | | 3661 | | 2.35 | | 64 | |
| (기준) jipda uniform | | | | | 2992 | | 1.08 | | 12 |

판정: **개선** (조건 A True: lam1000_map True, lam200_map True; 조건 B True: lam1000_uniform:gospa_mean_m True, lam1000_uniform:false_tracks_per_scan True, lam5_map:gospa_mean_m True, lam5_map:false_tracks_per_scan True, lam5_uniform:gospa_mean_m True, lam5_uniform:false_tracks_per_scan True)

## 평균

| 조건 | 방법 | seed | 가짜 항적 /scan | GOSPA (m) | 놓친 표적 /scan | ID switch | 확정 지연 (s) | 위치 RMSE (m) | 실행 시간 (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lam1000_map | jipda | 20 | 3.97 | 3817 | 2.61 | 31.35 | 39.12 | 188 | 76.20 |
| lam1000_map | jipda_est | 20 | 28.34 | 7755 | 2.59 | 50.30 | 24.04 | 203 | 213 |
| lam1000_map | jipda_map | 20 | 13.10 | 5800 | 3.17 | 34.35 | 45.83 | 191 | 774 |
| lam1000_map | jipda_amap | 20 | 4.38 | 3959 | 2.75 | 31.25 | 40.28 | 189 | 74.21 |
| lam1000_uniform | jipda | 20 | 1.38 | 2870 | 2.07 | 36.30 | 31.58 | 185 | 19.14 |
| lam1000_uniform | jipda_est | 20 | 1.37 | 2883 | 2.12 | 35.75 | 32.09 | 185 | 19.33 |
| lam1000_uniform | jipda_map | 20 | 105 | 11480 | 2.44 | 85.35 | 31.95 | 201 | 335 |
| lam1000_uniform | jipda_amap | 20 | 1.36 | 2906 | 2.19 | 35.75 | 33.40 | 185 | 25.05 |
| lam200_map | jipda | 20 | 1.33 | 2565 | 1.36 | 31.45 | 22.06 | 176 | 18.64 |
| lam200_map | jipda_est | 20 | 57.95 | 10846 | 1.40 | 35.25 | 21.29 | 181 | 13.24 |
| lam200_map | jipda_map | 20 | 8.88 | 4295 | 1.62 | 39.80 | 23.72 | 184 | 17.42 |
| lam200_map | jipda_amap | 20 | 1.44 | 2632 | 1.42 | 31.25 | 22.85 | 176 | 15.39 |
| lam5_map | jipda | 20 | 0.93 | 2055 | 0.59 | 30.35 | 9.62 | 172 | 0.67 |
| lam5_map | jipda_est | 20 | 0.90 | 2173 | 0.88 | 30.05 | 14.23 | 173 | 0.70 |
| lam5_map | jipda_map | 20 | 0.88 | 2255 | 1.08 | 29.70 | 16.46 | 174 | 0.71 |
| lam5_map | jipda_amap | 20 | 0.90 | 2178 | 0.88 | 30.20 | 14.39 | 173 | 2.58 |
| lam5_uniform | jipda | 20 | 0.89 | 2125 | 0.78 | 27.90 | 13.07 | 172 | 0.64 |
| lam5_uniform | jipda_est | 20 | 0.88 | 2160 | 0.86 | 28.40 | 14.18 | 174 | 0.69 |
| lam5_uniform | jipda_map | 20 | 0.86 | 2241 | 1.06 | 26.80 | 16.50 | 174 | 0.69 |
| lam5_uniform | jipda_amap | 20 | 0.88 | 2159 | 0.86 | 28.45 | 14.15 | 174 | 2.56 |

## 짝 차이

| 조건 | 차이 | 쌍 | 가짜 항적 /scan | GOSPA (m) | 놓친 표적 /scan | ID switch | 확정 지연 (s) | 위치 RMSE (m) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| lam1000_map | jipda_amap-jipda | 20 | +0.40 [+0.09, +0.71] | +141 [+70, +213] | +0.14 [+0.10, +0.18] | -0.10 [-1.23, +1.03] | +1.16 [+0.39, +1.93] | +1.70 [+0.32, +3.08] |
| lam1000_map | jipda_amap-jipda_est | 20 | -23.96 [-26.98, -20.94] | -3796 [-4188, -3405] | +0.16 [+0.11, +0.22] | -19.05 [-21.62, -16.48] | +16.25 [+15.19, +17.30] | -13.52 [-15.44, -11.60] |
| lam1000_map | jipda_amap-jipda_map | 20 | -8.72 [-9.58, -7.86] | -1841 [-1998, -1684] | -0.41 [-0.51, -0.31] | -3.10 [-5.01, -1.19] | -5.54 [-6.49, -4.59] | -1.28 [-3.13, +0.57] |
| lam1000_uniform | jipda_amap-jipda | 20 | -0.01 [-0.04, +0.02] | +35.93 [+23.65, +48.21] | +0.11 [+0.09, +0.14] | -0.55 [-1.33, +0.23] | +1.82 [+1.35, +2.29] | +0.28 [-0.34, +0.90] |
| lam1000_uniform | jipda_amap-jipda_est | 20 | -0.01 [-0.04, +0.02] | +22.75 [+6.65, +38.85] | +0.07 [+0.03, +0.11] | +0.00 [-0.87, +0.87] | +1.31 [+0.67, +1.95] | +0.31 [-0.29, +0.92] |
| lam1000_uniform | jipda_amap-jipda_map | 20 | -104 [-106, -102] | -8574 [-8814, -8334] | -0.25 [-0.31, -0.19] | -49.60 [-54.55, -44.65] | +1.45 [+0.59, +2.31] | -15.73 [-17.62, -13.83] |
| lam200_map | jipda_amap-jipda | 20 | +0.12 [+0.07, +0.16] | +66.94 [+49.04, +84.85] | +0.06 [+0.04, +0.08] | -0.20 [-0.89, +0.49] | +0.79 [+0.42, +1.16] | +0.10 [-0.39, +0.59] |
| lam200_map | jipda_amap-jipda_est | 20 | -56.50 [-61.17, -51.84] | -8214 [-8635, -7792] | +0.02 [-0.01, +0.04] | -4.00 [-5.26, -2.74] | +1.56 [+0.53, +2.58] | -4.64 [-6.09, -3.18] |
| lam200_map | jipda_amap-jipda_map | 20 | -7.44 [-8.14, -6.73] | -1662 [-1784, -1541] | -0.20 [-0.24, -0.16] | -8.55 [-11.76, -5.34] | -0.87 [-1.72, -0.02] | -7.51 [-9.21, -5.81] |
| lam5_map | jipda_amap-jipda | 20 | -0.03 [-0.03, -0.02] | +123 [+119, +127] | +0.29 [+0.29, +0.30] | -0.15 [-0.85, +0.55] | +4.77 [+4.64, +4.90] | +0.89 [+0.31, +1.47] |
| lam5_map | jipda_amap-jipda_est | 20 | +0.00 [+0.00, +0.01] | +4.44 [+2.37, +6.51] | +0.01 [+0.00, +0.01] | +0.15 [-0.23, +0.53] | +0.16 [+0.11, +0.20] | +0.04 [-0.09, +0.17] |
| lam5_map | jipda_amap-jipda_map | 20 | +0.02 [+0.02, +0.03] | -76.94 [-80.59, -73.30] | -0.20 [-0.21, -0.19] | +0.50 [-0.57, +1.57] | -2.07 [-2.23, -1.92] | -0.54 [-1.06, -0.03] |
| lam5_uniform | jipda_amap-jipda | 20 | -0.02 [-0.02, -0.01] | +33.83 [+31.08, +36.59] | +0.08 [+0.08, +0.09] | +0.55 [-0.12, +1.22] | +1.08 [+1.03, +1.14] | +1.62 [+1.16, +2.08] |
| lam5_uniform | jipda_amap-jipda_est | 20 | +0.00 [-0.00, +0.00] | -1.35 [-2.33, -0.37] | -0.00 [-0.01, -0.00] | +0.05 [-0.13, +0.23] | -0.03 [-0.07, +0.01] | +0.01 [-0.09, +0.11] |
| lam5_uniform | jipda_amap-jipda_map | 20 | +0.01 [+0.01, +0.02] | -82.60 [-88.81, -76.39] | -0.20 [-0.22, -0.19] | +1.65 [+0.76, +2.54] | -2.35 [-2.48, -2.22] | -0.07 [-0.59, +0.44] |

- lam1000_map JIPDA-amap / JIPDA: 가짜 항적 1.101, GOSPA 1.037, ID switch 0.997
- lam1000_uniform JIPDA-amap / JIPDA: 가짜 항적 0.991, GOSPA 1.013, ID switch 0.985
- lam200_map JIPDA-amap / JIPDA: 가짜 항적 1.088, GOSPA 1.026, ID switch 0.994
- lam5_map JIPDA-amap / JIPDA: 가짜 항적 0.972, GOSPA 1.060, ID switch 0.995
- lam5_uniform JIPDA-amap / JIPDA: 가짜 항적 0.982, GOSPA 1.016, ID switch 1.020
- lam1000_map 메움 비율 jipda_map: 가짜 항적 0.626, GOSPA 0.497
- lam1000_map 메움 비율 jipda_amap: 가짜 항적 0.983, GOSPA 0.964
- lam200_map 메움 비율 jipda_map: 가짜 항적 0.867, GOSPA 0.791
- lam200_map 메움 비율 jipda_amap: 가짜 항적 0.998, GOSPA 0.992
- 메움 비율은 JIPDA-est가 JIPDA보다 가짜 항적과 GOSPA 모두 10% 넘게 나쁜 조건에서만 계산한다.

## 일반화 확인: KATL_1106_peak (판정과 별도)

| 조건 | 방법 | seed | 가짜 항적 /scan | GOSPA (m) | 놓친 표적 /scan | ID switch | 확정 지연 (s) | 위치 RMSE (m) | 실행 시간 (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| KATL lam1000_map | jipda | 8 | 4.79 | 5350 | 7.51 | 218 | 40.43 | 196 | 109 |
| KATL lam1000_map | jipda_est | 8 | 27.07 | 8469 | 7.51 | 340 | 31.96 | 221 | 328 |
| KATL lam1000_map | jipda_map | 8 | 13.05 | 6948 | 9.37 | 207 | 50.28 | 200 | 1026 |
| KATL lam1000_map | jipda_amap | 8 | 6.37 | 5715 | 7.91 | 221 | 41.59 | 201 | 83.00 |
| KATL lam1000_uniform | jipda | 8 | 2.81 | 4799 | 6.96 | 196 | 39.37 | 185 | 31.32 |
| KATL lam1000_uniform | jipda_est | 8 | 2.79 | 4826 | 7.13 | 194 | 40.32 | 184 | 27.57 |
| KATL lam1000_uniform | jipda_amap | 8 | 2.74 | 4887 | 7.49 | 192 | 42.05 | 184 | 32.20 |

| 조건 | 차이 | 쌍 | 가짜 항적 /scan | GOSPA (m) | 놓친 표적 /scan | ID switch | 확정 지연 (s) | 위치 RMSE (m) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| KATL lam1000_map | jipda_amap-jipda | 8 | +1.57 [+0.77, +2.38] | +365 [+237, +493] | +0.40 [+0.29, +0.51] | +3.25 [-3.64, +10.14] | +1.16 [+0.20, +2.12] | +4.73 [+2.63, +6.83] |
| KATL lam1000_map | jipda_amap-jipda_est | 8 | -20.71 [-26.10, -15.31] | -2754 [-3393, -2115] | +0.40 [+0.17, +0.63] | -119 [-161, -77] | +9.63 [+6.68, +12.57] | -19.79 [-26.94, -12.64] |
| KATL lam1000_map | jipda_amap-jipda_map | 8 | -6.68 [-8.04, -5.33] | -1233 [-1424, -1042] | -1.45 [-1.62, -1.29] | +13.75 [+5.22, +22.28] | -8.69 [-9.84, -7.54] | +1.18 [-2.19, +4.56] |
| KATL lam1000_uniform | jipda_amap-jipda | 8 | -0.07 [-0.10, -0.04] | +88.90 [+72.58, +105.22] | +0.53 [+0.47, +0.59] | -3.25 [-6.03, -0.47] | +2.68 [+2.09, +3.27] | -0.59 [-2.39, +1.21] |
| KATL lam1000_uniform | jipda_amap-jipda_est | 8 | -0.05 [-0.11, +0.01] | +61.64 [+42.87, +80.40] | +0.36 [+0.27, +0.44] | -1.50 [-4.33, +1.33] | +1.73 [+1.15, +2.31] | -0.03 [-1.13, +1.07] |
- KATL lam1000_map 메움 비율 jipda_map: 가짜 항적 0.629, GOSPA 0.488
- KATL lam1000_map 메움 비율 jipda_amap: 가짜 항적 0.929, GOSPA 0.883
- KATL lam1000_map JIPDA-amap / JIPDA: 가짜 항적 1.328, GOSPA 1.068
- KATL lam1000_uniform JIPDA-amap / JIPDA: 가짜 항적 0.974, GOSPA 1.019

출처 파일: `results/stage3/b1/EHAM_1106_eval__jipda__lam1000_map.json`, `results/stage3/b1/EHAM_1106_eval__jipda__lam1000_uniform.json`, `results/stage3/b1/EHAM_1106_eval__jipda__lam200_map.json`, `results/stage3/b1/EHAM_1106_eval__jipda__lam5_map.json`, `results/stage3/b1/EHAM_1106_eval__jipda__lam5_uniform.json`, `results/stage3/b1/EHAM_1106_eval__jipda_est__lam1000_map.json`, `results/stage3/b1/EHAM_1106_eval__jipda_est__lam1000_uniform.json`, `results/stage4/eval/EHAM_1106_eval__jipda_est__lam200_map.json`, `results/stage4/eval/EHAM_1106_eval__jipda_est__lam5_map.json`, `results/stage4/eval/EHAM_1106_eval__jipda_est__lam5_uniform.json`, `results/stage4/eval/EHAM_1106_eval__jipda_map__lam1000_map.json`, `results/stage4/eval/EHAM_1106_eval__jipda_map__lam1000_uniform.json`, `results/stage4/eval/EHAM_1106_eval__jipda_map__lam200_map.json`, `results/stage4/eval/EHAM_1106_eval__jipda_map__lam5_map.json`, `results/stage4/eval/EHAM_1106_eval__jipda_map__lam5_uniform.json`, `results/stage4/katl/KATL_1106_peak__jipda__lam1000_map.json`, `results/stage4/katl/KATL_1106_peak__jipda_est__lam1000_map.json`, `results/stage4/katl/KATL_1106_peak__jipda_map__lam1000_map.json`, `results/stage5/eval/EHAM_1106_eval__jipda_amap__lam1000_map.json`, `results/stage5/eval/EHAM_1106_eval__jipda_amap__lam1000_uniform.json`, `results/stage5/eval/EHAM_1106_eval__jipda_amap__lam200_map.json`, `results/stage5/eval/EHAM_1106_eval__jipda_amap__lam5_map.json`, `results/stage5/eval/EHAM_1106_eval__jipda_amap__lam5_uniform.json`, `results/stage5/katl/KATL_1106_peak__jipda__lam1000_uniform.json`, `results/stage5/katl/KATL_1106_peak__jipda_amap__lam1000_map.json`, `results/stage5/katl/KATL_1106_peak__jipda_amap__lam1000_uniform.json`, `results/stage5/katl/KATL_1106_peak__jipda_est__lam1000_uniform.json`
