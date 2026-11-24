# Radar Track Lab 5단계 사전 등록: 클러터 지도 고치기(JIPDA-amap)와 원뿔 유지 v2

**이 실험은 4단계 결과(`docs/reports/2026-11-23-radar-clutter-map.md`, 브랜치 hyh4867/radar-clutter-map ca2a6df)를 보고 세운 후속 실험이다.** 4단계에서 드러난 두 약점(고른 클러터에서 JIPDA-map 붕괴, KATL에서 원뿔 유지의 낮은 회복률)을 겨냥해 방법을 고쳤다. 따라서 이 결과는 4단계와 독립된 첫 시험이 아니다. 평가 구간과 seed는 4단계와 같다.

작성: 2026-11-23 KST, 실행 전. 브랜치 hyh4867/radar-stage5. 결과는 `results/stage5/`에 둔다. 1–4단계 결과 파일과 동결 설정(`configs/stage3.yaml`, `configs/stage4.yaml`)은 바꾸지 않는다.

## 1. 이 문서를 쓰기 전에 본 것

- 4단계 보고서와 결과 전부(`results/stage4/summary.md`, `cone_summary.md`, `cone_diag.json`). 수치는 지시문 배경과 같다.
- 동작 확인용 실행 3개. 판정에 쓰지 않고 결과 파일도 남기지 않는다.
  - 원뿔 유지 v2 스크립트, EHAM_1106_eval seed 20261106 한 개: H1 EKF ID switch 28, H2 IMM 16. 평가 구간 seed를 하나 본 것이다.
  - JIPDA-amap(n_min 5, τ 30), 조정 구간 EHAM_1106_tune lam5_map seed 20271106 한 개: 가짜 항적 0.73/scan, 1.4 s. 선택에 쓰지 않는 조건이다.
- 조정 구간 EHAM_1106_tune의 참 고도로 잰 수직 속도(scan 사이 차분, 9,991개): 중앙값 6.7 ft/s, 99% 63.5 ft/s, 최댓값 96.3 ft/s. 2부의 수직 속도 상한(100 ft/s)을 정하는 데만 썼다.

## 2. 1부 방법: JIPDA-amap (`src/radar_track_lab/jpda.py` AdaptiveClutterMapDensity)

- 바탕은 4단계 ClutterMapDensity 그대로다. 1 km × 1.5° 칸, 지수 망각 C←aC+c, N←aN+1, a=e^(−1/τ)이다.
- 칸마다 창을 넓힌다. 창은 (2k_r+1) × (2k_a+1)칸이고 k = 0, 1, 2, …에서 k_r = min(k, K_r), k_a = min(k, K_a)이다. 창 안의 C 합(지수 가중 개수 합, "유효 개수")이 n_min 이상이 되는 첫 k에서 멈춘다.
- 상한은 3단계 거친 칸(10 km × 22.5°) 안에 들어가는 가장 큰 창이다. 홀수 칸 수라서 1 km × 1.5° 칸에서는 K_r = 4(9 km), K_a = 7(22.5°)이다. 상한 창에서도 n_min에 못 미치면 상한 창 값을 쓴다.
- 창은 거리 끝에서 잘리고(그만큼 부피가 줄어든다) 방위는 0/360°를 넘어 이어진다.
- 밀도 = max(창의 C 합 / (N × 창 부피 합), 바닥값). 바닥값, 제외 규칙(연관 확률 합 0.5 미만인 탐지만 지도에 넣음), JIPDA 동결값은 4단계와 같다. 첫 scan 전 값도 4단계와 같다(1/칸 부피).
- 지도는 scan마다 한 번 다시 계산한다(누적합으로 창 합 계산).

## 3. 단위 시험 (실데이터 실행 전에 통과)

`tests/test_stage5_amap.py`:
- 상한 반폭(1 km × 1.5° → 4, 7; 2 km × 3° → 2, 3)
- 넓히기가 n_min에서 멈춤(1×1 → 3×3 → 5×5), 상한 창 값 사용, 바닥값 유지
- 방위 0/360° 이어짐, 거리 끝 자르기
- 누적합 창 합이 직접 합과 같음
- 고른 합성 클러터(λ 1000/scan, 300 scan, τ 30)에서 추정 밀도 중앙값이 참값 ±8% 안. 참값 절반 미만 칸 비율이 2% 미만이고 4단계 지도의 1/5 미만. n_min 20이 n_min 5보다 흩어짐이 작음.

`tests/test_stage5_cone_v2.py`:
- 고도 창 상수, 수직 속도 최소제곱 추정(잘라냄, 짧은 기록은 0, 30 s 창, 100 ft 양자화)
- 고도 확인 게이트(창 경계, 고도 없는 보고 거절)
- H1이 4단계처럼 원뿔을 통과해 항적을 유지함
- 유지 중이거나 막 나온 항적이 다른 고도 보고와 고도 없는 보고를 받지 않음
- H2만 상승 중 항공기를 원뿔 진입으로 판단함

## 4. 1부 선택 (조정 구간만)

- 후보: n_min {5, 20} × τ {30, 100}, 4개(n5_30, n5_100, n20_30, n20_100). 칸 크기 1 km × 1.5°, 상한 10 km × 22.5°는 고정이다.
- 실행: EHAM_1106_tune, 측정 모형 M0, seed 20271106–20271110, 조건 lam1000_map과 lam1000_uniform. 결과는 `results/stage5/tune/`.
- JIPDA 기준값: lam1000_map은 4단계 파일(`results/stage4/tune/EHAM_1106_tune__jipda__lam1000_map.json`)을 쓴다. lam1000_uniform은 없으므로 같은 seed로 새로 돌린다.
- 점수 = max(GOSPA_map / JIPDA GOSPA_map, GOSPA_uniform / JIPDA GOSPA_uniform). GOSPA는 seed 5개 평균이다. 점수가 가장 작은 후보를 고른다. 동점(소수 넷째 자리까지 같음)이면 두 조건의 가짜 항적 합이 작은 쪽을 고른다.
- 고른 값은 `scripts/stage5_select.py --write`가 `configs/stage5.yaml`에 쓴다. 커밋해 동결한 뒤 평가를 시작한다.

## 5. 1부 평가와 판정

### 5.1 평가 실행
- 구간 EHAM_1106_eval, 측정 모형 M0, seed 20261106–20261125(20개). 조건은 lam1000_map, lam1000_uniform, lam200_map, lam5_map, lam5_uniform이다. JIPDA-amap만 새로 돌린다.
- 비교 대상은 모두 기존 파일이다.
  - JIPDA: `results/stage3/b1/` 다섯 조건
  - JIPDA-est: lam1000 두 조건은 `results/stage3/b1/`, 나머지 셋은 4단계 새 실행 `results/stage4/eval/`
  - 4단계 JIPDA-map: `results/stage4/eval/`

### 5.2 판정 (수치 규칙)
- **조건 A**: lam1000_map과 lam200_map 각각에서, JIPDA-amap의 GOSPA seed 평균이 JIPDA-est보다 낮다. 그리고 짝 차이(JIPDA-amap − JIPDA-est)의 95% t-구간 상한이 0보다 작다.
- **조건 B**: lam1000_uniform, lam5_map, lam5_uniform 각각에서, JIPDA-amap / JIPDA 비율이 GOSPA와 가짜 항적(false_tracks_per_scan) 모두 1.10 이하다. 비율은 seed 평균의 비율이다. 6개 비율이 모두 1.10 이하여야 한다.
- **개선**: A와 B를 모두 만족. **부분 개선**: 하나만 만족. **개선 없음**: 둘 다 불만족. 어긋난 항목을 적는다.
- 미리 적어 두는 위험: λ5에서는 추정 밀도가 거의 바닥값이고 바닥값은 바꾸지 않았다. 4단계 JIPDA-map의 lam5_map GOSPA 비율이 이미 1.097이었으므로, 조건 B는 λ5에서 경계에 걸릴 수 있다.

### 5.3 판정과 별도로 적는 것
- 4단계 JIPDA-map 대비 짝 차이(다섯 조건)
- 메움 비율 = (JIPDA-est − JIPDA-amap) / (JIPDA-est − JIPDA). 4단계 규칙대로 JIPDA-est가 JIPDA보다 10% 넘게 나쁜 조건에서만 계산한다.
- 놓친 표적, ID switch, 확정 지연, 실행 시간
- 그림 하나. 평가 구간 seed 20261106의 마지막 scan에서 lam1000_uniform과 lam1000_map 각각의 JIPDA-map, JIPDA-amap 추정 밀도 / 참 밀도를 보인다.

### 5.4 일반화 확인 (판정과 별도, 2부 다음, 시간이 남을 때)
- KATL_1106_peak, M0, lam1000_map과 lam1000_uniform, seed 20261106–20261113(8개).
- JIPDA-amap을 두 조건 모두 돌린다.
- lam1000_map의 JIPDA와 JIPDA-est는 4단계 파일(`results/stage4/katl/`)을 쓴다. lam1000_uniform의 JIPDA와 JIPDA-est는 새로 돌린다.
- 04:30 KST까지 끝나지 않을 것 같으면 lam1000_uniform을 먼저 돌린다. 고른 클러터에서의 붕괴가 고치려던 문제이기 때문이다. seed 수를 줄이면 줄인 수를 보고서에 적는다.

## 6. 퇴행 확인 (코드 변경 뒤, 조정 전)

같은 코드로 다음을 seed 2개(20261106, 20261107)로 다시 돌리고, seed별 summary의 모든 수치가 기존 파일과 같은지(상대 1e-9) 본다.
- JIPDA, JIPDA-est: EHAM_1106_eval lam1000_map, `results/stage3/b1/`과 비교
- 4단계 JIPDA-map(c1_1.5_30): EHAM_1106_eval lam200_map, `results/stage4/eval/`과 비교. lam1000_map은 seed당 13분이라 lam200_map을 쓴다.
- 4단계 원뿔 유지(ekf_cone, imm_cone)와 M4(ekf, imm): EHAM_1106_eval과 KATL_1106_peak, `results/stage4/cone/`과 비교. 비교 항목은 ID switch, misses 잃음, 15 km 안 misses 잃음, summary 전체다. 실행은 이 단계의 스크립트(`scripts/stage5_cone_run.py`)로 한다.

## 7. 2부 방법: 원뿔 유지 v2 (`src/radar_track_lab/cone.py` ConeHoldV2Mixin)

1부 평가 보고서를 push한 뒤에 시작한다.

### 7.1 H1: 4단계 유지 + 고도 확인
- 원뿔 진입 판단, 유지 시간 T_max, 유지 대상(확정 항적이고 Mode C를 아는 항적)은 4단계와 같다.
- **고도 확인 대상**은 유지 중인 항적과, 유지되었다가 아직 갱신되지 않은 항적("막 원뿔을 나온")이다. 대상 항적은 Mode C 고도가 예측 고도 ±Δh 안인 표적 보고와만 연관할 수 있다. 첫 갱신을 받으면 대상에서 빠진다.
  - 예측 고도 = 마지막 Mode C + v_z × (보고 시각 − 마지막 Mode C 시각)
  - Δh = 200 ft + 50 ft/s × (보고 시각 − 마지막 Mode C 시각). 200 ft는 Mode C 100 ft 양자화 두 칸이다. 50 ft/s는 수직 속도 추정 오차와 변화에 대한 여유다(지시문 예와 같음).
  - v_z: 그 항적의 최근 30 s Mode C 기록에 대한 최소제곱 기울기다. 기록이 2개 미만이거나 9.6 s(2 scan)보다 짧으면 0이다. ±100 ft/s로 자른다(1절의 조정 구간 최댓값 96.3 ft/s).
  - 고도가 없는 보고(허위 탐지)는 대상 항적에 붙지 않는다.
- **4단계와 다른 점 (해석)**: 4단계의 유지 항적은 연관에서 빠졌다. H1의 유지 항적은 고도 확인을 거친 보고라면 받을 수 있다. 지시문의 "유지 중이거나 막 원뿔을 나온 항적은 … 표적 보고만 받는다"를 그렇게 읽었다. 유지 중 보고를 받지 못하면 miss 수는 늘지 않는다(4단계와 같음).
- **Mode C를 연관에 쓴다.** 4단계는 Mode C를 원뿔 판단에만 썼다. H1부터는 실제 SSR 추적처럼 정보를 하나 더 쓴다. Mode C 오차(오류 보고, 누락)는 여전히 넣지 않으므로 실제보다 유리한 조건이다.

### 7.2 H2: H1 + 고도 외삽으로 원뿔 진입 판단
- 원뿔 진입 판단과 T_max 계산에 마지막 Mode C 대신 외삽 고도(마지막 Mode C + v_z × 경과 시간)를 쓴다. 나머지는 H1과 같다. 상승 중인 항공기가 유지 대상에서 빠지는 문제를 겨냥한다. 설명용이며 판정에 쓰지 않는다.

## 8. 2부 평가와 판정

### 8.1 실행
- 측정 모형 M4. 구간은 13개다: EHAM_1106_eval과 3단계 표본 밖 12개(EGLL_1106_peak, EGLL_1111_same, EHAM_1106_busy2, EHAM_1111_same, ENGM_1106_peak, ENGM_1111_same, KATL_1106_peak, KATL_1111_same, LSZH_1106_peak, LSZH_1111_same, YSSY_1106_peak, YSSY_1111_same).
- EKF와 IMM, seed 20261106–20261125(20개).
- 방법: M4(유지 없음), 4단계 유지, H1, H2를 13개 구간 모두 이 단계 스크립트로 돌린다. 원뿔 끔은 3단계 diag_near에 없는 11개 구간만 새로 돌리고, EHAM_1106_eval과 KATL_1106_peak은 `results/stage3/diag_near/`를 쓴다.
- 결과: `results/stage5/cone/`.

### 8.2 지표
- 회복률 = (M4 − 방법) / (M4 − 원뿔 끔). ID switch seed 평균이다. 구간은 seed 묶음 bootstrap 10,000회(난수 seed 0)로 구한다.
- M4 − 원뿔 끔이 run당 1.0 미만인 구간은 분모가 작아 회복률을 "해당 없음"으로 적는다. 그런 구간은 판정 1·2에 쓰지 않는다(판정 1·2는 KATL과 EHAM만 쓴다).
- 그 밖에 ID switch 원인별 개수(특히 "가까운 다른 항공기와 바뀜", near_other), 가짜 항적, GOSPA, RMSE, 놓친 표적, 고도 게이트가 거절한 쌍 수.

### 8.3 판정 (H1만)
- **개선**: 아래 넷을 모두 만족.
  1. KATL_1106_peak에서 EKF와 IMM 모두 회복률 50% 이상(점 추정)
  2. EHAM_1106_eval에서 EKF와 IMM 모두 회복률 80% 이상
  3. 13개 구간 모두, EKF와 IMM 각각, 가짜 항적 seed 평균이 M4의 1.10배 이하(26개 비율)
  4. EKF ID switch seed 평균이 M4보다 적은 구간이 13개 중 11개 이상
- **부분 개선**: 넷을 다 만족하지는 않지만, KATL에서 H1이 4단계 유지보다 낫다. 짝 차이(H1 − 4단계 유지) ID switch의 95% t-구간 상한이 EKF와 IMM 모두 0보다 작아야 한다.
- **개선 없음**: 그 밖의 경우.
- H2는 같은 수치를 보이기만 하고 판정하지 않는다.

## 9. 예측

### 9.1 에이전트(Claude, 이 문서 작성자) 예측
1부:
- 선택: n_min 20, τ 30. 점수는 lam1000_map 비율(4단계 1.5 안팎)이 좌우할 것이다. 몰린 구역 칸은 이미 개수가 많아 넓혀지지 않는다. 드문 배경은 n_min이 클수록 잡음이 줄어 유리하다.
- lam1000_uniform 가짜 항적: scan당 1.6 (1.3–3)
- lam1000_map: 가짜 항적 11 (7–15), GOSPA 5,500 m (4,800–6,300). 4단계(13.1)보다 조금 낫다. 확정 항적이 클러터를 먹어 밀도를 낮게 잡는 되먹임은 그대로 남는다고 본다.
- lam200_map GOSPA: 3,900 m (3,000–4,500)
- lam5_map GOSPA 비율(JIPDA 대비): 1.09 (1.05–1.12)
- 판정: 개선 30%, 부분 개선 65%, 개선 없음 5%. A는 거의 확실하다(90%). B는 λ5 GOSPA와 uniform 가짜 항적이 경계라서 35%로 본다.

2부:
- H1 KATL 회복률: EKF 50% (35–70%), IMM 45% (30–65%)
- H1 EHAM 회복률: EKF 90%, IMM 85%
- H1 KATL "가까운 다른 항공기와 바뀜"(EKF): run당 32 (29–37)
- H1 KATL EKF 가짜 항적 / M4: 1.10 (1.04–1.14). 판정 3은 반반이다.
- H2는 H1보다 KATL 회복률이 5%p 안팎 높을 것이다.
- H1 판정: 개선 20%, 부분 개선 60%, 개선 없음 20%.

### 9.2 검수자(Claude) 독립 예측 (지시문 그대로)
- 1순위 선택: n_min 20, τ 100
- JIPDA-amap, lam1000_uniform 가짜 항적: scan당 2 (1.3–4)
- JIPDA-amap, lam1000_map 가짜 항적: scan당 14 (10–20), GOSPA 6,000 m (5,300–7,000)
- JIPDA-amap, lam200_map GOSPA: 3,500 m (2,800–4,600)
- H1, KATL 회복률(EKF): 55% (35–75%)
- H1, KATL "가까운 다른 항공기와 바뀜": run당 32 (28–37)

## 10. 해석 (지시가 모호했던 곳)
- **유효 개수**: 지수 가중 개수 C의 창 합으로 정했다. 정상 상태 τ 30에서 고른 lam1000의 1 km × 1.5° 칸은 약 1.3개다.
- **상한**: 홀수 칸 창이 10 km × 22.5°를 넘지 않도록 9 km × 22.5°로 정했다. 거리 쪽이 1 km 작다.
- **"1.10배 이하"**: seed 평균의 비율로 정했다(4단계와 같음).
- **조건 A의 lam200_map JIPDA-est**: 4단계에서 새로 돌린 파일을 쓴다. 4단계에서는 판정 밖 참고였지만, 이번 지시는 조건 A에 lam200_map을 넣었다.
- **2부 판정 3**: "13개 구간 모두"를 EKF와 IMM 각각에 적용했다(엄한 쪽).
- **2부 부분 개선과 개선 없음**: 지시문에 없어서 8.3처럼 정했다.
- **원뿔 끔 seed**: diag_near와 같은 20개다.

## 11. 실행 규칙
- 다른 세션(ASTRA, 이어서 드론 학습)과 동시에 돈다. heavy-run 잠금은 쓰지 않는다. 시뮬레이션은 동시에 최대 2개 프로세스로 돌린다.
- 긴 실행 전에 `scripts/stage4_guard.sh`로 확인한다. 스왑이 3 GB를 넘거나 여유 메모리가 10% 미만이면 5분씩 기다린다. 다른 세션의 프로세스는 건드리지 않는다.
- screen과 caffeinate -i로 돌리고 seed마다 저장한다.
- 04:30 KST 이후에는 새 긴 실행을 시작하지 않는다. 06:00까지 끝나지 않으면 거기까지를 보고한다.
- 사이트, 공개 저장소, main은 건드리지 않는다.
- 진행 순서: 퇴행 확인 → 1부 조정 → 동결·커밋 → 1부 평가 → 보고서 1차 push → 2부 → (시간이 남으면) 1부 KATL.

## 12. 덧붙임 (실행 중, 시각 순)
- 18:17 퇴행 확인 통과: 11개 파일, seed 2개씩, 모든 비교 항목이 같음(`results/stage5/regression.json`).
- 18:27 조정 끝. 선택은 n20_30(점수 1.006; map 1.001, uniform 1.006)이다(`results/stage5/tune_selection.json`). `configs/stage5.yaml`에 동결해 커밋한 뒤 평가를 시작했다. 조정 실행이 예상(seed당 약 10분)보다 훨씬 빨라서(map seed당 30–40 s) 평가 일정을 앞당겼다. 판정 규칙은 바꾸지 않았다.
- 18:47 1부 평가 끝, 19:05 1부 보고서 push(ef6ee58). 그 뒤 2부를 시작했다(19:06–19:27).
- 19:27 KATL 일반화 시작. 시간이 충분해 seed 8개, 두 조건을 모두 돌렸다(19:40 끝).
