# Radar Track Lab 보완: 자료로 추정한 세밀한 클러터 지도 (JIPDA-map)

작성: 2026-11-23, 무인 밤샘 작업. 브랜치 `hyh4867/radar-clutter-map`.

## 세 줄 요약

1. **판정: 부분 개선**(사전 등록 5.3).
   - 맞은 것: lam1000_map에서 GOSPA가 JIPDA-est보다 1,955 m 낮다 [−2,372, −1,538]. λ 5 두 조건에서 가짜 항적과 ID switch가 JIPDA의 1.10배 안이다.
   - 어긋난 것: 가짜 항적이 scan당 13.10으로 기준 8을 넘는다.
2. **핵심 수치**(스히폴 평가 구간, seed 20개):
   - lam1000_map 가짜 항적/scan: JIPDA(참 밀도) 3.97, JIPDA-est 28.34, JIPDA-map 13.10. JIPDA-est와 JIPDA 사이 간격 중 가짜 항적은 63%, GOSPA는 50%를 메웠다.
   - 고른 클러터 lam1000_uniform에서는 크게 나빠졌다: 가짜 항적 105.2/scan(JIPDA 1.38), GOSPA 11,480 m(JIPDA 2,870 m).
3. **남은 문제**:
   - 조정 규칙(lam1000_map의 GOSPA만 봄)이 가장 작은 칸과 가장 짧은 기억(1 km × 1.5°, τ 30)을 골랐다. 이 설정은 클러터가 성긴 곳에서 칸당 개수가 너무 적어 밀도를 낮게 추정하고, 그래서 고른 클러터에서 실패한다.
   - 칸 크기를 자료량에 맞추는 방법(최소 개수, 거친 칸으로의 수축)은 해 보지 않았다.
   - λ 5에서 놓친 표적(+0.28–0.49/scan)과 확정 지연(+3.4–6.8 s)도 JIPDA보다 나쁘다.

**우선순위 2(원뿔 안을 아는 항적 유지, 9절)**: 1순위 보고서를 02:58에 push한 뒤 실행했다.
- 원뿔이 만든 ID switch 증가분 가운데 스히폴에서 EKF 89.3% [76.4, 103.7], IMM 81.1%를 되찾았다.
- KATL에서는 EKF 36.5% [22.2, 51.3], IMM 31.0%에 그쳤다.
- KATL에서는 가짜 항적이 11.9%(EKF) 늘어 부작용 기준 10%를 넘었다.

## 1. 한 일

| 순서 | 내용 | 결과 | commit |
|---|---|---|---|
| 1 | 브랜치 `hyh4867/radar-clutter-map`을 `hyh4867/Radar` 0c96e4c에서 만듦 | 결과는 `results/stage4/`. 3단계 파일과 `configs/stage3.yaml`은 바꾸지 않음 | — |
| 2 | 사전 등록 `docs/PREREGISTRATION_4.md` 작성·push(조정·평가 실행 전) | 후보 8개, 선택 규칙, 판정 기준, 에이전트·검수자 예측 | 7c0b069 |
| 3 | 추정기 `ClutterMapDensity`(`src/radar_track_lab/jpda.py`), `jipda_map` 방법(`sim.py`), 단위 시험 6개(`tests/test_stage4_clutter_map.py`) | 칸 경계, 망각 계산, 바닥값, 합성 지도 클러터 수렴, 고른 클러터 수렴 | 7c0b069 |
| 3 | 퇴행 확인: JIPDA·JIPDA-est, 평가 구간 lam1000_map, seed 2개 | summary 지표 19개 × seed 2 × 방법 2 모두 3단계와 차이 0 (`results/stage4/regression.json`) | 6453669 |
| 4 | 조정(EHAM_1106_tune, seed 20271106–20271110, lam1000_map) | **c1_1.5_30** 선택. 설정은 `configs/stage4.yaml`에 동결 | d810f7b |
| 4 | 평가(EHAM_1106_eval, seed 20개, 다섯 조건) | `results/stage4/summary.md` | 2931275 |
| 5 | 일반화 확인(KATL_1106_peak lam1000_map) | 아래 4절 | d3a9bf6 |
| 6 | 그림(추정 밀도 대 참 밀도) | `results/stage4/figures/density_map.png` | ccabad4 |

방법 요약:
- JIPDA-map은 3단계 JIPDA(동결값 p0 0.01, confirm 0.95, delete 0.01, p_survive 0.98, pd 0.9)와 같다. 다른 것은 클러터 밀도 ρ(z)뿐이다.
- 밀도는 거리 × 방위 칸마다 "확정 항적과의 연관 확률 합 < 0.5"인 탐지점을 센 지수 망각 평균이다. 망각은 C ← a·C + c, N ← a·N + 1, a = e^(−1/τ)이고, 칸 밀도 = max(C/(N·부피), 바닥값)이다.
- 바닥값은 JIPDA-est와 같은 밀도인 2.546e-5 /(m·rad)/scan이다.
- 추정기에는 참 밀도도, 클러터 모형도, 고정 구역 위치도 주지 않았다.

## 2. 선택 (조정 구간만)

출처는 `results/stage4/tune_selection.json`과 `results/stage4/tune/`이고, 값은 seed 5개의 평균이다.

| 후보 | GOSPA (m) | 가짜 항적 /scan | 놓친 표적 /scan | ID switch | seed당 시간 (s) |
|---|---:|---:|---:|---:|---:|
| **c1_1.5_30** (선택) | 5,317 | 9.86 | 4.38 | 13.4 | 643 |
| c1_1.5_100 | 5,385 | 10.32 | 4.27 | 14.2 | 390 |
| c1_3_100 | 5,571 | 11.40 | 3.98 | 12.4 | 131 |
| c1_3_30 | 5,725 | 12.19 | 4.07 | 11.4 | 191 |
| c2_1.5_100 | 6,216 | 14.95 | 4.04 | 13.2 | 147 |
| c2_1.5_30 | 6,292 | 15.41 | 4.08 | 12.8 | 199 |
| c2_3_30 | 6,568 | 17.36 | 4.05 | 12.4 | 196 |
| c2_3_100 | 6,597 | 17.69 | 3.97 | 12.0 | 173 |
| (참고) JIPDA, 참 밀도 | 3,661 | 2.35 | 3.72 | 10.4 | 64 |
| (참고) JIPDA-est | 7,620 | 26.87 | 3.80 | 10.8 | 228 |

조정 구간에서는 칸이 작을수록 좋았다. 거리 칸 1 km가 2 km보다, 방위 칸 1.5°가 3°보다 나았다. τ의 영향은 작았다.

## 3. 평가 결과 (스히폴 평가 구간, M0, seed 20261106–20261125)

출처는 `results/stage4/summary.md`(`summary.json`)이고, `scripts/stage4_report.py`가 만들었다.
- JIPDA와 JIPDA-est(lam1000 두 조건)는 3단계 파일 `results/stage3/b1/`이다.
- JIPDA-map과 JIPDA-est(lam200_map, lam5 두 조건)는 이번 실행 `results/stage4/eval/`이다.
- [ ]는 seed 짝 차이의 95% t-구간이다.

### 3.1 평균

| 조건 | 방법 | 가짜 항적 /scan | GOSPA (m) | 놓친 표적 /scan | ID switch | 확정 지연 (s) | seed당 시간 (s) |
|---|---|---:|---:|---:|---:|---:|---:|
| lam1000_map | JIPDA | 3.97 | 3,817 | 2.61 | 31.35 | 39.1 | 76 (3단계) |
| lam1000_map | JIPDA-est | 28.34 | 7,755 | 2.59 | 50.30 | 24.0 | 213 (3단계) |
| lam1000_map | **JIPDA-map** | **13.10** | **5,800** | 3.17 | 34.35 | 45.8 | 774 |
| lam1000_uniform | JIPDA | 1.38 | 2,870 | 2.07 | 36.30 | 31.6 | 19 (3단계) |
| lam1000_uniform | JIPDA-est | 1.37 | 2,883 | 2.12 | 35.75 | 32.1 | 19 (3단계) |
| lam1000_uniform | **JIPDA-map** | **105.21** | **11,480** | 2.44 | 85.35 | 32.0 | 335 |
| lam200_map | JIPDA | 1.33 | 2,565 | 1.36 | 31.45 | 22.1 | 19 (3단계) |
| lam200_map | JIPDA-est (새 실행) | 57.95 | 10,846 | 1.40 | 35.25 | 21.3 | 13 |
| lam200_map | **JIPDA-map** | **8.88** | **4,295** | 1.62 | 39.80 | 23.7 | 17 |
| lam5_map | JIPDA | 0.93 | 2,055 | 0.59 | 30.35 | 9.6 | 0.7 |
| lam5_map | JIPDA-est (새 실행) | 0.90 | 2,173 | 0.88 | 30.05 | 14.2 | 0.7 |
| lam5_map | **JIPDA-map** | **0.88** | **2,255** | 1.08 | 29.70 | 16.5 | 0.7 |
| lam5_uniform | JIPDA | 0.89 | 2,125 | 0.78 | 27.90 | 13.1 | 0.6 |
| lam5_uniform | JIPDA-est (새 실행) | 0.88 | 2,160 | 0.86 | 28.40 | 14.2 | 0.7 |
| lam5_uniform | **JIPDA-map** | **0.86** | **2,241** | 1.06 | 26.80 | 16.5 | 0.7 |

### 3.2 짝 차이 (JIPDA-map − 비교 대상)

| 조건 | 대상 | 가짜 항적 /scan | GOSPA (m) | 놓친 표적 /scan | ID switch | 확정 지연 (s) |
|---|---|---:|---:|---:|---:|---:|
| lam1000_map | JIPDA-est | −15.24 [−18.38, −12.11] | −1,955 [−2,372, −1,538] | +0.57 [+0.48, +0.66] | −15.95 [−19.27, −12.63] | +21.8 [+20.2, +23.4] |
| lam1000_map | JIPDA | +9.12 [+8.38, +9.87] | +1,982 [+1,860, +2,104] | +0.56 [+0.47, +0.64] | +3.00 [+1.08, +4.92] | +6.7 [+5.8, +7.7] |
| lam1000_uniform | JIPDA | +104 [+102, +106] | +8,610 [+8,368, +8,852] | +0.37 [+0.30, +0.43] | +49.05 [+44.37, +53.73] | +0.4 [−0.7, +1.5] |
| lam200_map | JIPDA | +7.55 [+6.83, +8.28] | +1,729 [+1,603, +1,856] | +0.26 [+0.22, +0.30] | +8.35 [+5.13, +11.57] | +1.7 [+0.9, +2.5] |
| lam200_map | JIPDA-est (새 실행) | −49.07 [−53.68, −44.45] | −6,551 [−6,981, −6,122] | +0.21 [+0.17, +0.26] | +4.55 [+1.07, +8.03] | +2.4 [+1.7, +3.2] |
| lam5_map | JIPDA | −0.05 [−0.05, −0.04] | +200 [+195, +204] | +0.49 [+0.48, +0.51] | −0.65 [−1.74, +0.44] | +6.8 [+6.7, +7.0] |
| lam5_uniform | JIPDA | −0.03 [−0.03, −0.03] | +116 [+110, +122] | +0.28 [+0.27, +0.30] | −1.10 [−1.90, −0.30] | +3.4 [+3.3, +3.6] |

### 3.3 판정 (사전 등록 5.3)

| 항목 | 기준 | 값 | 결과 |
|---|---|---|---|
| 1 | lam1000_map 가짜 항적 ≤ 8 /scan | 13.10 | 어긋남 |
| 2 | lam1000_map GOSPA < JIPDA-est이고 짝 구간 상한 < 0 | −1,955 [−2,372, −1,538] | 맞음 |
| 3 | λ 5 가짜 항적 ≤ 1.10 × JIPDA | map 0.949, uniform 0.966 | 맞음 |
| 4 | λ 5 ID switch ≤ 1.10 × JIPDA | map 0.979, uniform 0.961 | 맞음 |

→ **부분 개선**(2를 만족, 1은 어긋남).

판정과 별도로 적기로 한 것(5.3):
- **"고른 클러터에서 손해 없음"(JIPDA 대비 비율 ≤ 1.10): 아니다.**
  - lam1000_uniform: 가짜 항적 76.5배, GOSPA 4.00배.
  - lam200_map: 가짜 항적 6.69배, GOSPA 1.67배.
- 메움 비율은 JIPDA-est가 JIPDA보다 두 지표 모두 10% 넘게 나쁜 조건에서만 계산했다.
  - lam1000_map: 가짜 항적 0.626, GOSPA 0.497.
  - lam200_map: 가짜 항적 0.867, GOSPA 0.791. 이 조건의 JIPDA-est는 새 실행이다.
- λ 5의 비용: 놓친 표적이 JIPDA보다 +0.49(map), +0.28(uniform) /scan 많고, 확정 지연은 +6.8 s, +3.4 s 길다. GOSPA는 +200 m, +116 m(5–10%)다. 가짜 항적은 조금 적다.

### 3.4 왜 고른 클러터에서 무너지나 (설명, 별도 시험은 하지 않음)

- 그림 `results/stage4/figures/density_map.png`(lam1000_map, seed 20261106, 마지막 scan):
  - 거리별 방위 평균은 참 밀도와 거의 겹친다.
  - 칸 하나하나를 보면 성긴 곳(40 km 밖 고른 배경)이 얼룩덜룩하다.
- 클러터 개수로 가중한 칸 비교(`results/stage4/density_map.json`):

  | | JIPDA-est | JIPDA-map |
  |---|---:|---:|
  | 추정/참 중앙값 | 0.88 | 0.66 |
  | 2배 안에 드는 클러터 비율 | 64% | 86% |
  | 절반 미만으로 추정된 칸에 떨어진 클러터 | 31% | 11% |

- 연관 가중치는 w ∝ 1/ρ̂이다. 평균이 맞아도 ρ̂가 잡음으로 작아진 칸에서는 클러터 하나의 가중치가 몇 배로 커진다.
- 고른 λ 1000에서 1 km × 1.5° 칸 하나의 기대 개수는 scan당 0.042개다. τ 30의 유효 표본 수(약 2τ)를 곱해도 2.5개 정도라 상대 잡음이 60%대다.
- 지도 클러터에서는 허위 탐지의 90%가 레이더 근처와 고정 구역에 몰려 있다. 거기서는 칸당 개수가 충분해 작은 칸이 이득이었다.
- 조정은 그 조건만 봤다. 그래서 고른 클러터에 필요한 "큰 칸 또는 긴 기억"은 선택될 수 없었다.
- 이 설명은 수치와 맞지만, 칸 크기를 바꾼 평가 구간 실행으로 따로 확인하지는 않았다. 평가 구간에서 다른 후보를 돌리는 것은 사전 등록 밖이다.

### 3.5 실행 시간

- JIPDA-map은 lam1000_map에서 seed당 774 s였다. 같은 밤 조정 구간의 JIPDA-est는 228 s였다. 칸이 작을수록 느렸다(조정 표 참고).
- 원인은 확인하지 않았다. 추정기 자체는 칸 하나를 읽고 쓰는 계산이라, 성긴 칸에서 ρ̂가 작아져 임시 항적이 늘어난 결과로 보인다.
- 다른 세션(ASTRA 학습)과 CPU를 나눠 쓴 밤이므로, 3단계 실행 시간과 직접 비교하지 않는다.

## 4. 일반화 확인: KATL_1106_peak lam1000_map (판정과 별도)

출처: `results/stage4/katl/KATL_1106_peak__{jipda,jipda_est,jipda_map}__lam1000_map.json`(JIPDA-map seed 20261112–20261113은 `katl_p2/`에서 합침), `results/stage4/summary.md`. 애틀랜타, 2026-11-06 15:10–15:40 UTC, M0, 지도 클러터 λ 1000(공항 키로 만든 고정 구역 배치), seed 20261106–20261113(8개, 사전 등록 10절 규칙).

| 방법 | 가짜 항적 /scan | GOSPA (m) | 놓친 표적 /scan | ID switch | 확정 지연 (s) | seed당 시간 (s) |
|---|---:|---:|---:|---:|---:|---:|
| JIPDA (참 밀도) | 4.79 | 5,350 | 7.51 | 218 | 40.4 | 109 |
| JIPDA-est | 27.07 | 8,469 | 7.51 | 340 | 32.0 | 328 |
| JIPDA-map | 13.05 | 6,948 | 9.37 | 207 | 50.3 | 1,026 |

짝 차이(JIPDA-map − 대상):
- 대 JIPDA-est: 가짜 항적 −14.02 [−19.31, −8.74], GOSPA −1,521 [−2,146, −896] m, 놓친 표적 +1.86 [+1.60, +2.11], ID switch −132 [−174, −91], 확정 지연 +18.3 [+15.0, +21.7] s.
- 대 JIPDA: 가짜 항적 +8.26 [+6.80, +9.72], GOSPA +1,598 [+1,389, +1,808] m, 놓친 표적 +1.86 [+1.63, +2.09], ID switch −10.5 [−18.1, −2.9], 확정 지연 +9.9 [+8.0, +11.7] s.
- 메움 비율: 가짜 항적 0.629, GOSPA 0.488. 스히폴(0.626, 0.497)과 거의 같다.

KATL에서도 순서는 JIPDA < JIPDA-map < JIPDA-est(가짜 항적, GOSPA)이고, 가짜 항적은 scan당 13으로 기준 8을 넘는다. 놓친 표적은 KATL에서 더 늘었다(+1.86/scan, JIPDA의 1.25배). ID switch는 JIPDA보다 조금 적은데, 놓친 표적이 늘어난 것과 함께 보면 확정이 늦어 바뀔 기회가 줄어든 결과일 수 있다(확인 안 함). seed 8개라 구간이 스히폴보다 넓다.

## 5. 예측 대 실제

| 항목 | 에이전트 예측 | 검수자 예측 | 실제 |
|---|---|---|---|
| 선택 | 2 km × 3° × τ 100 | — | 1 km × 1.5° × τ 30 (틀림. 조정 구간에서 c2_3_100은 8개 중 꼴찌) |
| lam1000_map 가짜 항적 /scan | 8 (4–20) | 6 (3–12) | 13.10 (에이전트 범위 안, 검수자 범위 밖) |
| lam1000_map GOSPA | 4,500 m (3,900–6,000) | 4,300 m (3,800–5,500) | 5,800 m (에이전트 범위 안, 검수자 범위 밖) |
| lam1000_uniform 가짜 항적 /scan | 1.5 (1.3–2.5) | JIPDA 1.38의 ±20% (1.10–1.66) | 105.21 (둘 다 크게 틀림) |
| λ 5 판정 3·4 | 만족 (75%) | — | 만족 |
| λ 5 확정 지연 | +1–3 s | — | +3.4 s, +6.8 s (예측보다 큼) |
| 종합 | 개선 50%, 부분 개선 40%, 개선 없음 10% | — | 부분 개선 |
| KATL 순서 (가짜 항적) | JIPDA < JIPDA-map < JIPDA-est | — | JIPDA 4.79 < JIPDA-map 13.05 < JIPDA-est 27.07 (맞음) |

- 에이전트 예측에서 고른 배경이 문제라는 짐작은 맞았다. 다만 그 효과의 크기(지도 클러터의 배경 10%가 아니라 고른 클러터 전체)와 칸 크기 선택은 틀렸다.
- 검수자와 에이전트 모두 고른 클러터에서 손해가 작다고 예측했는데, 실제로는 가장 크게 무너진 조건이었다.

## 6. 사전 등록과 달라진 점, 실행 세부

- **변경 없음**: 후보, 선택 규칙, 평가 조건, seed, 판정 기준은 사전 등록 그대로다.
- **seed 나눠 돌리기**(실행 방식만): 느린 세 조건(lam1000_map, lam1000_uniform, lam200_map의 JIPDA-map과 lam200_map JIPDA-est)은 seed 20261106–20261115를 레인 0에서, 20261116–20261125를 레인 1에서 돌렸다. 레인 1 결과(`results/stage4/eval_p2/`)는 `scripts/stage4_merge.py`로 `results/stage4/eval/`에 합쳤다. 합친 파일의 `merged_from`에 출처를 적었다.
- **코드 버전 기록**: 평가 파일의 `code.commit`은 실행 시작 때의 HEAD(d810f7b)다. seed별 `codes`는 각 seed를 저장할 때의 HEAD(일부 a589dc4)다.
  - 그 사이 커밋은 쓰이지 않는 새 파일 `cone.py`(우선순위 2)와 문서·스크립트뿐이다.
  - `git diff --stat 7c0b069 HEAD -- src configs`의 결과는 `cone.py` 추가와 `configs/stage4.yaml` 동결 블록뿐이다.
  - 조정 파일 4개의 `dirty: true`는 그때 큐 스크립트(`scripts/stage4_queue_eval.sh`)를 고치고 있었기 때문이다. src는 같았다.
- **퇴행 확인을 돌린 상태**: 7c0b069와 같은 내용을 커밋하기 직전 작업 트리에서 돌렸다(기록상 0c96e4c + dirty). 결과 파일 경로는 `results/stage4/regression/`이다.
- **KATL seed 수**: 규칙대로 8개(사전 등록 10절). JIPDA-map은 두 레인에 나눠 돌렸다.
- **메모리 규칙**: 스왑 3 GB 초과로 5분 대기 1회(01:32, KATL 레인 1 시작 전). 러너의 여유 15% 대기는 0초.
- KATL JIPDA-map 프로세스는 약 2 GB까지 커졌다(01:33 측정). 그때 여유 메모리는 78%였다.
- **메움 비율 계산 범위**: 처음 만든 보고 스크립트는 다섯 조건 모두에서 계산했다. 간격이 없는 조건(lam1000_uniform, λ 5)에서 뜻 없는 값(예: 20,375)이 나와, "JIPDA-est가 두 지표 모두 10% 넘게 나쁜 조건에서만"으로 좁혔다. 결과를 본 뒤에 바꾼 표시 규칙이고, 판정과는 무관하다.

- **우선순위 2 실행 세부**:
  - 퇴행 확인은 사전 등록(seed 2개)보다 넓혀 seed 20개로 했다. 부작용 비교에 M4 summary 지표가 필요했기 때문이다(3단계 diag_near 파일에는 ID switch 관련 값만 있음).
  - 9.3의 원인 분류는 결과를 본 뒤에 한 사후 분석이다.

## 7. 테스트

`.venv/bin/python -m pytest -v`, 01:30 KST, 이 브랜치(우선순위 2 시험 포함): **83 passed in 38.04s**. 실패와 건너뜀은 없다. 우선순위 2 실행 뒤 03:04에 `-q`로 다시 돌린 결과도 83 passed in 29.78s다(그 사이에는 스크립트만 추가됨).

```
============================= test session starts ==============================
platform darwin -- Python 3.12.8, pytest-9.2.0, pluggy-1.7.0 -- <project>/.venv/bin/python
cachedir: .pytest_cache
rootdir: <project>
configfile: pyproject.toml
testpaths: tests
collecting ... collected 83 items

tests/test_audit.py::test_update_common_sample_with_asynchronous_times_and_exclusions PASSED [  1%]
tests/test_audit.py::test_scan_end_common_sample_drops_the_hard_pair_and_can_flip_the_comparison PASSED [  2%]
tests/test_audit.py::test_duplicate_and_mismatched_keys_are_errors PASSED [  3%]
tests/test_audit.py::test_paired_difference_and_percent_reduction_by_hand PASSED [  4%]
tests/test_audit.py::test_unpaired_target_is_excluded_from_the_scan_end_sample PASSED [  6%]
tests/test_audit.py::test_recording_does_not_change_scores_and_reproduces_both_rmses[ekf] PASSED [  7%]
tests/test_audit.py::test_recording_does_not_change_scores_and_reproduces_both_rmses[nn] PASSED [  8%]
tests/test_audit.py::test_recording_does_not_change_scores_and_reproduces_both_rmses[imm] PASSED [  9%]
tests/test_audit.py::test_prediction_only_baseline_extrapolates_the_last_two_detections_by_hand PASSED [ 10%]
tests/test_audit.py::test_prediction_only_baseline_shares_the_baseline_association_and_leaves_its_scores_alone PASSED [ 12%]
tests/test_audit.py::test_three_way_common_scan_end_sample PASSED        [ 13%]
tests/test_audit.py::test_ekf_hold_output_reports_the_last_updated_position_and_shares_the_ekf_updates PASSED [ 14%]
tests/test_audit.py::test_ekf_hold_output_position_by_hand PASSED        [ 15%]
tests/test_ekf_tracker.py::test_single_target_straight_line_converges PASSED [ 16%]
tests/test_ekf_tracker.py::test_ekf_reduces_error_vs_raw_measurement PASSED [ 18%]
tests/test_ekf_tracker.py::test_gate_threshold_and_mahalanobis PASSED    [ 19%]
tests/test_ekf_tracker.py::test_gating_rejects_far_detection PASSED      [ 20%]
tests/test_ekf_tracker.py::test_hungarian_assignment_global_optimum PASSED [ 21%]
tests/test_ekf_tracker.py::test_m_of_n_confirmation_and_deletion PASSED  [ 22%]
tests/test_ekf_tracker.py::test_track_ids_persist_and_are_not_reused PASSED [ 24%]
tests/test_ekf_tracker.py::test_componentwise_assignment_matches_dense_solve PASSED [ 25%]
tests/test_geo.py::test_azimuth_convention_clockwise_from_north PASSED   [ 26%]
tests/test_geo.py::test_polar_cartesian_round_trip PASSED                [ 27%]
tests/test_geo.py::test_wrap_pi PASSED                                   [ 28%]
tests/test_geo.py::test_polar_cov_cross_range PASSED                     [ 30%]
tests/test_geo.py::test_geodetic_enu_round_trip_and_scale PASSED         [ 31%]
tests/test_geo.py::test_velocity_rotation_meridian_convergence PASSED    [ 32%]
tests/test_imm.py::test_transition_matrix_is_a_markov_semigroup PASSED   [ 33%]
tests/test_imm.py::test_ct_predict_exact_circle_small_omega_and_jacobian PASSED [ 34%]
tests/test_imm.py::test_turn_is_detected_and_tracked_better_than_cv PASSED [ 36%]
tests/test_imm.py::test_straight_line_accuracy_not_worse_than_cv PASSED  [ 37%]
tests/test_imm.py::test_nees_on_model_matched_truth PASSED               [ 38%]
tests/test_imm.py::test_imm_single_target_management_like_ekf PASSED     [ 39%]
tests/test_metrics_repro.py::test_gospa_known_values PASSED              [ 40%]
tests/test_metrics_repro.py::test_same_seed_reproducible_and_different_seed_differs PASSED [ 42%]
tests/test_metrics_repro.py::test_clutter_rate_matches_lambda PASSED     [ 43%]
tests/test_metrics_repro.py::test_hermite_exact_for_constant_acceleration PASSED [ 44%]
tests/test_metrics_repro.py::test_anees_bounds_contain_dof PASSED        [ 45%]
tests/test_privacy.py::test_dbflags_exclusion PASSED                     [ 46%]
tests/test_stage2.py::test_extractor_writes_no_identifier_column PASSED  [ 48%]
tests/test_stage2.py::test_processed_point_files_hold_only_allowed_columns PASSED [ 49%]
tests/test_stage2.py::test_committed_outputs_carry_no_identifier_fields PASSED [ 50%]
tests/test_stage2.py::test_sites_are_outside_korea_and_extract_script_applies_dbflags PASSED [ 51%]
tests/test_stage2.py::test_truth_turn_rate_matches_the_known_manoeuvre PASSED [ 53%]
tests/test_stage2.py::test_lost_track_in_a_known_turn_is_classified_as_turn PASSED [ 54%]
tests/test_stage3_c2_breakdown.py::test_breakdown_definitions PASSED     [ 55%]
tests/test_stage3_c2_breakdown.py::test_breakdown_rejects_inconsistent_events PASSED [ 56%]
tests/test_stage3_jpda.py::test_two_tracks_one_shared_detection_by_hand PASSED [ 57%]
tests/test_stage3_jpda.py::test_exact_matches_brute_force_and_lbp_is_close PASSED [ 59%]
tests/test_stage3_jpda.py::test_single_track_jipda_reduces_to_ipda PASSED [ 60%]
tests/test_stage3_jpda.py::test_pda_update_reduces_to_kalman_with_one_certain_detection PASSED [ 61%]
tests/test_stage3_jpda.py::test_grid_density_floor_and_average PASSED    [ 62%]
tests/test_stage3_jpda.py::test_trackers_follow_ncv_targets[jpda] PASSED [ 63%]
tests/test_stage3_jpda.py::test_trackers_follow_ncv_targets[jipda] PASSED [ 65%]
tests/test_stage3_jpda.py::test_jipda_rejects_dense_clutter_better_than_gnn PASSED [ 66%]
tests/test_stage3_jpda.py::test_jipda_with_certain_existence_equals_jpda PASSED [ 67%]
tests/test_stage3_pregate.py::test_adaptive_pregate_equals_no_pregate_ekf[5.0] PASSED [ 68%]
tests/test_stage3_pregate.py::test_adaptive_pregate_equals_no_pregate_ekf[200.0] PASSED [ 69%]
tests/test_stage3_pregate.py::test_adaptive_pregate_equals_no_pregate_imm PASSED [ 71%]
tests/test_stage3_pregate.py::test_pregate_radius_by_hand PASSED         [ 72%]
tests/test_stage3_pregate.py::test_fixed_6km_drops_a_gated_pair_that_adaptive_keeps PASSED [ 73%]
tests/test_stage3_sensor.py::test_swerling1_pd_by_hand PASSED            [ 74%]
tests/test_stage3_sensor.py::test_swerling1_matches_monte_carlo PASSED   [ 75%]
tests/test_stage3_sensor.py::test_calibration_by_hand PASSED             [ 77%]
tests/test_stage3_sensor.py::test_horizon_by_hand PASSED                 [ 78%]
tests/test_stage3_sensor.py::test_slant_and_elevation_against_vector_geometry PASSED [ 79%]
tests/test_stage3_sensor.py::test_slant_to_ground_round_trip_and_mode_c PASSED [ 80%]
tests/test_stage3_sensor.py::test_clutter_map_fractions_and_near_mean PASSED [ 81%]
tests/test_stage3_sensor.py::test_clutter_map_density_integrates_to_lambda_and_is_fixed_per_site PASSED [ 83%]
tests/test_stage3_sensor.py::test_merge_groups_by_hand PASSED            [ 84%]
tests/test_stage3_sensor.py::test_simulate_merge_reports_one_detection_at_the_mean PASSED [ 85%]
tests/test_stage3_sensor.py::test_simulate_cone_of_silence_and_slant_correction PASSED [ 86%]
tests/test_stage3_sensor.py::test_all_elements_off_reproduces_the_stage_1_model PASSED [ 87%]
tests/test_stage4_clutter_map.py::test_cell_boundaries PASSED            [ 89%]
tests/test_stage4_clutter_map.py::test_exponential_forgetting_arithmetic PASSED [ 90%]
tests/test_stage4_clutter_map.py::test_floor_is_jipda_est_floor_density PASSED [ 91%]
tests/test_stage4_clutter_map.py::test_converges_to_true_map_density[1000.0-1.5-30.0] PASSED [ 92%]
tests/test_stage4_clutter_map.py::test_converges_to_true_map_density[2000.0-3.0-100.0] PASSED [ 93%]
tests/test_stage4_clutter_map.py::test_uniform_clutter_matches_uniform_density PASSED [ 95%]
tests/test_stage4_cone.py::test_hold_time_formula PASSED                 [ 96%]
tests/test_stage4_cone.py::test_with_modec_attaches_quantised_altitude_to_target_reports_only PASSED [ 97%]
tests/test_stage4_cone.py::test_track_held_through_cone_and_not_deleted PASSED [ 98%]
tests/test_stage4_cone.py::test_hold_expires_after_t_max PASSED          [100%]

============================= 83 passed in 38.04s ==============================
```

## 8. 남은 문제

- **고른 클러터 실패**: 칸 크기를 자료량에 맞추지 않으면 이 추정기는 쓸 수 없다. 다음 방법들은 해 보지 않았다.
  - 칸당 최소 개수가 찰 때까지 이웃 칸을 합치는 적응 칸.
  - 거친 격자(JIPDA-est) 추정으로의 수축.
  - 조정 기준에 고른 클러터 조건을 함께 넣는 것.
- **λ 5 비용**: 놓친 표적과 확정 지연이 JIPDA보다 나쁘다. 바닥값(2.5e-5)이 λ 5의 참 밀도(약 8e-6)보다 큰 것과, 작은 칸에서 아직 확정되지 않은 표적의 탐지점이 밀도로 잡히는 것이 원인으로 보인다. 확인하지는 않았다.
- **실행 시간**: lam1000_map에서 JIPDA보다 약 10배 느리다.
- **일반화**: 다른 공항은 KATL 하나, seed 8개만 봤다.
- 이 실험은 지도 클러터 모형(가까운 지수 + 고정 구역 6곳 + 고른 10%) 하나에서만 했다.

## 9. 우선순위 2: 원뿔 안을 아는 항적 유지

1순위 보고서(9d6e42a)를 02:58 KST에 push했으므로 지시대로 시작했다. 사전 등록 9절(a589dc4)은 실행 전인 22:05 KST에 커밋했다.

### 9.1 실행 가능 여부와 방법

- 추적기는 원래 (거리, 방위, 시각)만 받는다. 하지만 센서 모형 M2–M4는 표적 보고마다 Mode C 고도로 경사 거리를 고친다. 즉, 모의 레이더는 이미 Mode C를 갖고 있다. 그래서 이 값을 표적 보고에 붙여 넘겼다(`src/radar_track_lab/cone.py`, `with_modec`). 허위 탐지에는 붙이지 않았다.
  - 이 때문에 "고도가 있는 보고는 진짜 표적"이라는 정보가 생긴다. 고도는 원뿔 판단에만 쓰고, 연관과 항적 관리에는 쓰지 않았다.
- 확정 항적이 마지막 보고의 Mode C 고도를 갖고 있고 예측 위치의 고각이 42°를 넘으면 "유지"한다. 유지 중에는 연관하지 않고 M-of-N 계수도 멈춘다.
- 최대 유지 시간은 T_max = 2·r_c/max(|v|, 50 m/s) + 9.6 s, r_c = (고도 − 안테나 높이)/tan 42°이다.
- `scripts/stage4_cone_run.py`는 자기 프로세스 안에서만 `sim.simulate_scans`와 `sim.make_tracker`를 감싼다. `sim.py`는 바꾸지 않았다.
- 단위 시험 4개(`tests/test_stage4_cone.py`): T_max 식, Mode C 부착, 합성 상공 통과(보통 EKF는 확정 ID 2개, 유지 EKF는 1개), T_max < 0이면 유지 없음.
- 퇴행 확인: 유지를 끈 같은 경로로 M4 ekf·imm을 seed 20개 돌렸다. ID switch, misses 잃음, 15 km 안 misses 잃음이 3단계 `results/stage3/diag_near` M4와 80쌍 모두 같다(`results/stage4/cone/*__M4_regression__*.json`).

### 9.2 결과 (M4, seed 20261106–20261125)

출처는 `results/stage4/cone_summary.md`(`scripts/stage4_cone_report.py`)이다. 원뿔 끔 값은 3단계 `results/stage3/diag_near/*__M4_nocone__*.json`이다.

| 구간 | 방법 | ID switch M4 | 유지 | 원뿔 끔 | **회복률** [bootstrap 95%] | 짝 차이 유지 − M4 | misses 잃음 M4 → 유지 (끔) | 15 km 안 misses 잃음 M4 → 유지 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 스히폴 | EKF | 36.15 | 30.70 | 30.05 | **89.3%** [76.4, 103.7] | −5.45 [−6.43, −4.47] | 7.05 → 3.65 (2.10) | 4.95 → 1.55 |
| 스히폴 | IMM | 28.30 | 22.95 | 21.70 | **81.1%** [66.4, 96.3] | −5.35 [−6.78, −3.92] | 7.05 → 4.25 (2.00) | 5.05 → 2.25 |
| KATL | EKF | 210.80 | 203.75 | 191.50 | **36.5%** [22.2, 51.3] | −7.05 [−10.16, −3.94] | 25.50 → 16.00 (8.50) | 17.00 → 7.30 |
| KATL | IMM | 196.80 | 190.95 | 177.90 | **31.0%** [12.4, 47.8] | −5.85 [−9.71, −1.99] | 25.70 → 17.35 (8.60) | 17.10 → 8.65 |

유지된 항적-scan은 run당 93–95(스히폴), 455–475(KATL)였다. 유지 시간 초과는 0이었다.

부작용(유지 − M4, 비 = 유지/M4):
- 가짜 항적/scan:
  - 스히폴: EKF +0.039 [+0.029, +0.049] (1.033), IMM 1.021.
  - KATL: EKF +0.365 [+0.318, +0.413] (**1.119**), IMM 1.093.
  - 10%를 넘은 것은 KATL EKF 하나다.
- GOSPA는 네 경우 모두 1–2% 줄었다.
- 놓친 표적/scan은 12–19% 줄었다.
- 위치 RMSE는 2%(스히폴), 6%(KATL) 늘었다. 이 RMSE는 각자 표본 기준이라, 원뿔 안의 예측 위치가 표본에 들어간 영향일 수 있다.

### 9.3 KATL에서 회복이 낮은 이유 (사후 분석, 사전 등록 밖)

`scripts/stage4_cone_diag.py` → `results/stage4/cone_diag.json`(EKF, seed 20개, 3단계 원인 분류), run당 사건 수:

| 원인 | 스히폴 M4 → 유지 | KATL M4 → 유지 |
|---|---:|---:|
| misses | 7.05 → 3.65 | 25.50 → 16.00 |
| truth_gap | 8.95 → 8.50 | 123.95 → 114.95 |
| near_other (가까운 다른 항공기와 바뀜) | 6.30 → 4.70 | 29.20 → **38.65** |
| near_radar | 0.05 → 0.05 | 3.60 → 4.45 |
| unexplained | 0.10 → 0.10 | 1.25 → 2.45 |
| turn | 13.5 → 13.5 | 27.3 → 27.25 |

- KATL에서 유지는 misses와 truth_gap 사건을 18.5회 줄였다. 하지만 "가까운 다른 항공기와 바뀜"이 9.45회 늘어 이득의 절반쯤을 잃었다.
- 교통이 많은 KATL에서는 유지 중 공분산이 커진 항적이 원뿔을 나올 때 다른 항공기 보고를 잡는 경우가 많은 것으로 보인다. 사건 하나하나를 보고 확인한 것은 아니다.
- 남은 15 km 안 misses 잃음(KATL 7.3/run)은 모두 "누락된 scan이 전부 원뿔 안"인 사건이다. 그런데 유지 시간 초과는 0이다. 그러니 이 항적들은 유지 대상이 되지 못했다.
- 그 이유로는 다음이 가능하다. 모두 확인하지 않았다.
  - 확정 전이었다.
  - 고도를 아직 받지 못했다.
  - 상승 중이라 마지막 Mode C가 낮아 예측 고각이 42° 아래로 나왔다.
  - 예측 위치가 원뿔 경계 밖이었다.

### 9.4 예측 대 실제

| 항목 | 에이전트 예측 | 검수자 예측 | 실제 |
|---|---|---|---|
| 회복률 EKF | 65% (35–85%) | 60% (40–90%) | 스히폴 89.3%(둘 다 범위 밖, 위로), KATL 36.5%(에이전트 범위 안, 검수자 범위 밖) |
| 회복률 IMM | 60% (30–85%) | 60% (40–90%) | 스히폴 81.1%(둘 다 범위 안), KATL 31.0%(에이전트 범위 안, 검수자 범위 밖) |
| 스히폴과 KATL이 비슷 | 비슷 | — | 크게 다름 |

### 9.5 남은 문제 (우선순위 2)

- KATL의 "가까운 다른 항공기와 바뀜" 증가를 줄일 방법은 해 보지 않았다. 예를 들어 유지 항적의 게이트 상한, 또는 원뿔을 나올 때 고도 일치를 요구하는 방법이 있다.
- 유지 대상이 되지 못한 원뿔 손실(KATL 7.3/run)의 원인을 나누지 않았다.
- Mode C 오차는 넣지 않았다. 원뿔 판단은 이상적인 고도를 쓴다.
- JPDA/JIPDA에는 적용하지 않았다(지시 범위: EKF·IMM).

## 10. 사이트 문구 제안 (반영하지 않음)

현재 문구: "이 비교에서는 허위 탐지 밀도를 안다고 가정하고 실제 밀도 값을 입력했습니다."

제안: "이 비교에서는 허위 탐지 밀도를 안다고 가정하고 실제 밀도 값을 입력했습니다. 밀도를 탐지점에서 추정하면 성능이 떨어집니다. 허위 탐지를 한 구역에 몰아 넣은 조건에서 가짜 항적은 scan당 3.97(참 밀도) 대비 28.3(거친 격자 추정)과 13.1(세밀한 격자 추정)이었습니다. 세밀한 격자는 고르게 퍼진 허위 탐지에서 오히려 크게 나빠졌습니다(1.4 → 105)."

## 11. commit

브랜치 `hyh4867/radar-clutter-map`(시작점 `hyh4867/Radar` 0c96e4c):

| commit | 내용 |
|---|---|
| 7c0b069 | 사전 등록, 추정기, 단위 시험, 러너 |
| 6453669 | 퇴행 확인 결과, 큐·선택·보고·그림 스크립트 |
| d810f7b | 선택 동결(c1_1.5_30) |
| a589dc4 | 우선순위 2 사전 등록(9절)과 모듈·시험·러너(실행 전) |
| 2931275 | 평가 결과(다섯 조건 × seed 20) |
| 651fc31 | KATL seed 수 덧붙임(사전 등록 10절) |
| ccabad4 | 밀도 그림 |
| d3a9bf6 | KATL 결과 |
| 9d6e42a | 1순위 보고서(02:58 push) |
| 1e9c8dd | 우선순위 2 결과·사후 분석 |
| (이 커밋) | 보고서에 우선순위 2 절 추가 |
