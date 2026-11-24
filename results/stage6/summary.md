# 6단계 2부: 데이터로 정하는 바닥값 (JIPDA-amap)

`scripts/stage6_report.py`가 만든 파일. 스히폴 평가 구간, M0, seed 20개. amap5 = 5단계 JIPDA-amap(고정 바닥값), amap6 = 바닥값을 상한 창 추정에서 정한 것. [ ]는 짝 t-구간.

판정: **부분 개선** ((a) GOSPA 비 ≤ 1.01 다섯 조건: True — lam1000_map 0.9942, lam1000_uniform 1.0002, lam200_map 1.0000, lam5_map 0.9999, lam5_uniform 0.9999; (b) λ5 놓친 표적·확정 지연 감소: False — lam5_map:missed_per_scan True, lam5_map:init_delay_mean_s True, lam5_uniform:missed_per_scan False, lam5_uniform:init_delay_mean_s True)

선택(조정 구간, 점수 = lam5_map·lam1000_uniform GOSPA/JIPDA 중 큰 값): **f = 0.25**

| 후보 | 점수 | lam5_map 비 | lam1000_uniform 비 | lam5_map 놓친 표적 | lam5_map 확정 지연 (s) |
|---|---:|---:|---:|---:|---:|
| f=0.25 | 1.0669 | 1.067 | 1.006 | 0.974 | – |
| f=0.5 | 1.0669 | 1.067 | 1.006 | 0.974 | – |
| f=1.0 | 1.0669 | 1.067 | 1.008 | 0.974 | – |
| (참고) 5단계 고정 바닥값 | 1.0664 | 1.066 | 1.006 | 0.974 | – |

| 조건 | 방법 | false_tracks_per_scan | gospa_mean_m | missed_per_scan | id_switches | init_delay_mean_s | rmse_m |
|---|---|---:|---:|---:|---:|---:|---:|
| lam1000_map | jipda | 3.97 | 3817 | 2.61 | 31.35 | 39.12 | 188 |
| lam1000_map | amap5 | 4.38 | 3959 | 2.75 | 31.25 | 40.28 | 189 |
| lam1000_map | amap6 | 4.26 | 3935 | 2.78 | 31.00 | 40.25 | 189 |
| lam1000_uniform | jipda | 1.38 | 2870 | 2.07 | 36.30 | 31.58 | 185 |
| lam1000_uniform | amap5 | 1.36 | 2906 | 2.19 | 35.75 | 33.40 | 185 |
| lam1000_uniform | amap6 | 1.36 | 2906 | 2.19 | 35.75 | 33.43 | 185 |
| lam200_map | jipda | 1.33 | 2565 | 1.36 | 31.45 | 22.06 | 176 |
| lam200_map | amap5 | 1.44 | 2632 | 1.42 | 31.25 | 22.85 | 176 |
| lam200_map | amap6 | 1.44 | 2632 | 1.42 | 31.25 | 22.85 | 176 |
| lam5_map | jipda | 0.93 | 2055 | 0.59 | 30.35 | 9.62 | 172 |
| lam5_map | amap5 | 0.90 | 2178 | 0.88 | 30.20 | 14.39 | 173 |
| lam5_map | amap6 | 0.90 | 2177 | 0.88 | 30.15 | 14.37 | 173 |
| lam5_uniform | jipda | 0.89 | 2125 | 0.78 | 27.90 | 13.07 | 172 |
| lam5_uniform | amap5 | 0.88 | 2159 | 0.86 | 28.45 | 14.15 | 174 |
| lam5_uniform | amap6 | 0.88 | 2159 | 0.86 | 28.55 | 14.13 | 174 |

## 짝 차이 amap6 − amap5

| 조건 | false_tracks_per_scan | gospa_mean_m | missed_per_scan | id_switches | init_delay_mean_s | rmse_m |
|---|---:|---:|---:|---:|---:|---:|
| lam1000_map | -0.120 [-0.173, -0.066] | -23.140 [-33.008, -13.272] | +0.030 [+0.009, +0.050] | -0.250 [-0.585, +0.085] | -0.034 [-0.629, +0.562] | -0.049 [-0.381, +0.283] |
| lam1000_uniform | +0.000 [+0.000, +0.000] | +0.648 [-0.708, +2.003] | +0.002 [-0.002, +0.007] | +0.000 [+0.000, +0.000] | +0.036 [-0.039, +0.112] | +0.003 [-0.003, +0.009] |
| lam200_map | -0.000 [-0.001, +0.000] | +0.087 [-0.170, +0.344] | +0.000 [-0.000, +0.001] | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] | +0.022 [-0.026, +0.071] |
| lam5_map | +0.001 [-0.001, +0.003] | -0.162 [-0.869, +0.545] | -0.001 [-0.002, -0.000] | -0.050 [-0.155, +0.055] | -0.018 [-0.030, -0.006] | +0.003 [-0.064, +0.069] |
| lam5_uniform | +0.001 [+0.000, +0.002] | -0.111 [-1.055, +0.832] | -0.002 [-0.004, +0.000] | +0.100 [-0.044, +0.244] | -0.021 [-0.037, -0.004] | +0.051 [-0.011, +0.114] |

출처 파일: `results/stage3/b1/EHAM_1106_eval__jipda__lam1000_map.json`, `results/stage3/b1/EHAM_1106_eval__jipda__lam1000_uniform.json`, `results/stage3/b1/EHAM_1106_eval__jipda__lam200_map.json`, `results/stage3/b1/EHAM_1106_eval__jipda__lam5_map.json`, `results/stage3/b1/EHAM_1106_eval__jipda__lam5_uniform.json`, `results/stage5/eval/EHAM_1106_eval__jipda_amap__lam1000_map.json`, `results/stage5/eval/EHAM_1106_eval__jipda_amap__lam1000_uniform.json`, `results/stage5/eval/EHAM_1106_eval__jipda_amap__lam200_map.json`, `results/stage5/eval/EHAM_1106_eval__jipda_amap__lam5_map.json`, `results/stage5/eval/EHAM_1106_eval__jipda_amap__lam5_uniform.json`, `results/stage6/eval/EHAM_1106_eval__jipda_amap__lam1000_map.json`, `results/stage6/eval/EHAM_1106_eval__jipda_amap__lam1000_uniform.json`, `results/stage6/eval/EHAM_1106_eval__jipda_amap__lam200_map.json`, `results/stage6/eval/EHAM_1106_eval__jipda_amap__lam5_map.json`, `results/stage6/eval/EHAM_1106_eval__jipda_amap__lam5_uniform.json`
