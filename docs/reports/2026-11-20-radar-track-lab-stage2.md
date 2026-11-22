# 2026-11-20 Radar Track Lab 2단계 보고서

브랜치 `hyh4867/Radar`, `projects/radar-track-lab` 안에서만 작업했습니다. main 병합, 공개 저장소 반영, 데모 재배포, 사이트 변경은 하지 않았습니다. 웹 데모와 썸네일 파일은 건드리지 않았습니다.

범위는 1단계와 같습니다: 민간 공항 감시 레이더 시나리오, 위협 평가·무기 할당·요격 기능 없음, 군용·LADD·PIA 항공기는 추출 첫 단계에서 제외, 등록번호·편명·ICAO 주소 저장 안 함, 한국 상공과 군 시설 제외.

## 결론

| 질문 | 답 | 근거 (출처 파일) |
|---|---|---|
| Q1. 잃은 13.3회는 선회 때문인가 | 그렇다. 다만 68%가 좁게 도는 느린 항공기 두 대에서 나왔다 | 267건 중 265건(99.3%)이 선회 구간, 기저율 19.3%. `results/data/stage2/summary.json`의 q1, `lost_tracks_ekf_eval.csv` |
| Q2. IMM이 그 실패를 줄이는가 | 줄인다. 직선 정확도는 해치지 않는다. NEES는 나아지지 않았다 | 잃음 13.3 → 6.0회(짝 차이 −7.3 [−8.3, −6.4]), 직선 RMSE 비 0.985, 선회 RMSE 비 0.887, NEES 2.85 → 2.67. summary.json의 q2 |
| Q3. 독립 구현과 같은 답인가 | 조건부로 그렇다. 차이 두 가지를 찾았고 원인을 확인했다 | 아래 "Q3" 절. `stonesoup_compare.json` |
| Q4. 다른 공항·시간대에서도 유지되는가 | 유효 시나리오 12개 모두에서 유지 | EKF > 기준선 12/12, IMM 이득 12/12. summary.json의 q4 |
| Q5(선택). 엄격한 확정 규칙 | 사전 등록한 규칙으로는 바꿀 규칙이 없었다 | `tune_confirm.json`. 6/8 평가는 사전 등록 밖 탐색 |

## 한 일

1. **사전 등록** `docs/PREREGISTRATION_2.md`를 새 실행 전에 커밋했습니다(`12d2a1b`). 질문별 지표, 예측(모두 작성 에이전트의 예측), 판정 규칙, seed, 조정 구간, 시나리오 목록, 중단 조건을 적었습니다.
2. **Q1**: 1단계 EKF를 같은 seed 20개로 다시 돌려 1단계 수치를 그대로 재현한 뒤(RMSE 174.7 m, ID switch 24.9회, 분류 7.0 / 4.6 / 13.35), 잃은 항적 267건마다 정답 선회율, 탐지 누락 수, 가장 가까운 다른 표적 거리, 레이더 거리, 속력을 표로 만들었습니다.
3. **Q2**: IMM(등속 + 선회율을 상태에 둔 coordinated turn EKF)을 구현했습니다(`src/radar_track_lab/imm.py`). 정답을 아는 시험 6개를 먼저 통과시키고, 조정 구간(10:00–10:15 UTC)에서만 격자 64개를 seed 10개로 돌려 매개변수를 골라 `configs/stage2.yaml`에 동결했습니다(`af45ee2`). 그 뒤 평가 구간에서 EKF와 짝 비교했습니다.
4. **Q3**: Stone Soup 1.9.1(MIT)을 프로젝트 venv에만 설치했습니다(1초, numpy·scipy 버전 그대로). filter 단계와 추적기 단계(30분 × seed 3개)를 같은 탐지점으로 대조했습니다.
5. **Q4**: 디스크에 남아 있던 2026-11-06 원본에서 공항 8곳을 한 번에 추출했고(5분 26초), 2026-11-11 하루치(3.4 GiB)를 더 받아 같은 방식으로 추출했습니다. 매개변수를 동결한 뒤 표본 밖 시나리오 14개 × 방법 3개 × seed 20개를 돌렸습니다.
6. **Q5(선택)**: 확정 규칙 5개를 조정 구간에서 비교했습니다. JPDA·MHT는 설계 메모만 썼습니다(`docs/DESIGN_NOTE_JPDA_MHT.md`).
7. **산출물**: README(2단계 기준, 수치 블록은 실행 파일에서 생성), `results/RESULTS.md`(2단계 + 1단계 이력), 그림 4장, test 12개 추가.

## 결과 수치와 출처

모든 수치는 `results/data/stage2/` 아래 파일에서 스크립트가 만든 것입니다. 기준 조건(Pd 0.9, 클러터 λ 5/scan, σ_θ 0.15°), seed 20261106–20261125.

### Q1 (`summary.json` q1, `lost_tracks_ekf_eval.csv`)

- "표적이 있는데 잃음" 267건(run당 13.35회) 중 선회(창 안 최대 선회율 ≥ 1°/s) 265건, 탐지 누락 2회 이상 1건, 설명 안 됨 1건.
- 같은 창에 선회가 들어 있는 기저율은 19.3%입니다(5.1배). 사전 등록한 규칙으로 "선회가 주원인"입니다.
- 181건(68%)은 좁게 계속 도는 느린 항공기 두 대에서 나왔습니다(속력 중앙값 62, 74 m/s, 최대 선회율 중앙값 6.6, 9.6°/s). 나머지 38대는 86건(run당 4.3회), 속력 중앙값 124 m/s, 최대 선회율 중앙값 2.4°/s입니다.
- 151건은 같은 창에 탐지 누락이 1회 이상 있었습니다.

### Q2 (`tune_imm.json`, `runs/EHAM_1106_eval__{ekf,imm,nn}.json`, `timing.json`)

- 조정 결과: q_cv 25, q_ct 25, 선회율 과정 잡음 0.3°/s/√s, 평균 체류 시간 300 s(등속), 40 s(선회). 조정 구간 ID switch는 EKF 8.7회, IMM 3.5회.

| 지표 (평가 구간) | EKF | IMM | 짝 차이 IMM − EKF [95% 구간] |
|---|---:|---:|---:|
| ID switch (30분) | 24.9 ± 2.1 | 15.4 ± 1.4 | −9.5 [−11.0, −8.0] |
| ├ ADS-B 공백 뒤 | 7.0 | 7.0 | 0.0 |
| ├ 3 km 안에 다른 표적 | 4.6 ± 1.2 | 2.5 ± 0.9 | −2.1 [−3.2, −1.1] |
| └ 표적이 있는데 잃음 | 13.3 ± 1.6 | 6.0 ± 1.1 | −7.3 [−8.3, −6.4] |
| 항적 끊김 | 3.6 ± 0.7 | 2.1 ± 0.5 | −1.6 [−2.2, −0.9] |
| 위치 RMSE [m] | 174.7 ± 1.2 | 167.6 ± 1.2 | −7.0 [−7.7, −6.3] |
| ├ 직선 구간 [m] | 158.6 ± 1.1 | 156.1 ± 0.9 | 비 0.985 |
| └ 선회 구간 [m] | 273.4 ± 4.4 | 242.5 ± 4.4 | 비 0.887 |
| 놓친 표적 / scan | 0.82 | 0.82 | −0.01 |
| 가짜 항적 / scan | 1.08 | 1.04 | −0.03 |
| GOSPA [m] | 2,236 ± 10 | 2,191 ± 10 | −45 [−49, −40] |
| 실제 정답 평균 NEES | 2.85 | 2.67 | |
| 실행 시간 (30분 구간 1회) | 0.58 s | 0.80 s | 1.39배 |

- 잃은 항적을 나누면, 좁게 도는 두 대에서는 run당 9.05 → 5.05회, 나머지 항공기에서는 4.3 → 0.95회입니다.

### Q3 (`stonesoup_compare.json`)

- **filter 단계, 레이더가 원점인 좌표계**: 불일치. 위치 차 최대 2.2 m(직선 합성), 0.52 m(선회 합성), 0.25 m(실제 항공기 1대). 기준은 1 cm였습니다.
  - 원인은 Stone Soup 쪽입니다. 관측 Jacobian을 전진 차분으로 구하는 함수(`stonesoup.functions.jacobian`)가 좌표가 음수일 때 차분 간격을 1e-8 m로 잡습니다. 정확한 식과 비교한 상대 오차는 좌표가 모두 양수일 때 2×10⁻⁸, 음수 좌표가 있으면 1×10⁻³–8×10⁻³입니다.
- **filter 단계, 모든 좌표가 양수인 좌표계**(Stone Soup의 센서 위치 인자로 레이더를 (+200 km, +200 km)에 둠, Stone Soup 코드는 그대로): 일치. 위치 차 최대 0.05 mm, 속도 차 최대 7.7×10⁻⁶ m/s, 공분산 상대 차 최대 2.4×10⁻⁷.
- **추적기 단계, 비용 규칙을 맞춘 경우**(양수 좌표계): seed 3개 중 2개는 375 scan 모두 연관이 같고 확정 항적 위치가 전부 1 cm 안입니다. 나머지 1개(20261107)는 scan 125에서 연관 하나가 갈라졌습니다.
  - 원인은 이 프로젝트 쪽입니다. gate 앞에서 "예측 위치에서 6 km 안"인 쌍만 남기는데, 한 scan을 놓친 가항적의 χ² gate는 7–8 km라 6 km보다 넓습니다. 그 쌍(6,007 m, d² = 8.0)을 이 프로젝트는 버리고 Stone Soup은 연관했습니다.
  - 한도를 12 km로 넓히면 seed 3개 모두 연관이 같고 위치가 전부 1 cm 안이며 ID switch 수도 같습니다(25, 29, 24).
  - 한도를 넓혔을 때 이 프로젝트 지표의 변화(시나리오 4개 × 방법 2개 × seed 20개): 값이 바뀐 run은 20개 중 0–5개, 평균 차이는 ID switch 0.00회, RMSE 0.001 m 이하입니다(`summary.json` prune_check).
- **추적기 단계, Stone Soup의 GNN 배정 그대로**(Mahalanobis 거리의 합): 같은 가설에서 두 비용 규칙이 다른 짝을 고른 scan은 375개 중 2, 2, 4개. RMSE 차이 0.02 m 이내, ID switch 수 같음(25, 29, 24), GOSPA 차이 1–11 m.
- 원점 좌표계에서 비용을 맞춘 경우(seed 1개): 연관은 375 scan 모두 같고 지표도 같지만, 위치가 1 cm 안인 항적-scan은 28%입니다(Jacobian 오차 때문).

### Q4 (`scenarios.json`, `runs/*.json`, `summary.json` q4)

| 시나리오 (UTC) | 표적/scan | RMSE 기준선 / EKF / IMM [m] | ID switch EKF → IMM | 짝 차이 [95% 구간] |
|---|---:|---:|---:|---:|
| 스히폴 11-06 14:40 | 49.9 | 520 / 169 / 162 | 25.8 → 17.5 | −8.3 [−9.6, −7.0] |
| 런던 히스로 11-06 12:25 | 92.6 | 522 / 172 / 159 | 63.5 → 37.6 | −25.9 [−28.3, −23.6] |
| 애틀랜타 11-06 15:10 | 118.0 | 489 / 167 / 163 | 182.8 → 165.7 | −17.1 [−18.4, −15.8] |
| 취리히 11-06 11:10 | 40.8 | 561 / 162 / 150 | 31.9 → 17.0 | −14.9 [−16.4, −13.5] |
| 시드니 11-06 22:57 | 44.9 | 390 / 160 / 148 | 98.0 → 78.9 | −19.1 [−21.6, −16.6] |
| 오슬로 11-06 12:45 | 14.4 | 513 / 151 / 137 | 8.5 → 3.0 | −5.5 [−6.4, −4.5] |
| 스히폴 11-11 12:45 | 35.2 | 557 / 149 / 144 | 9.0 → 4.3 | −4.7 [−5.6, −3.7] |
| 런던 히스로 11-11 12:25 | 65.7 | 530 / 161 / 152 | 50.3 → 33.2 | −17.1 [−18.8, −15.4] |
| 애틀랜타 11-11 15:10 | 104.6 | 474 / 169 / 167 | 157.0 → 143.1 | −13.9 [−15.9, −11.9] |
| 취리히 11-11 11:10 | 22.4 | 624 / 152 / 150 | 8.4 → 5.8 | −2.5 [−3.2, −1.9] |
| 시드니 11-11 22:57 | 26.0 | 405 / 142 / 136 | 41.7 → 36.2 | −5.5 [−6.7, −4.3] |
| 오슬로 11-11 12:45 | 10.1 | 581 / 140 / 136 | 1.8 → 0.3 | −1.4 [−2.0, −0.9] |

- 유효 기준(scan당 5대 이상) 미달 2개: 스히폴 02:00(1.0대), 04:30(4.8대). 수치는 README 표에 있고 판정에서는 뺐습니다. 두 곳에서도 EKF는 기준선보다 나았고, IMM은 ID switch가 거의 없어 차이가 없었습니다.
- 깨진 곳은 없었습니다. 다만 이득의 크기는 곳마다 다릅니다. 애틀랜타와 시드니는 ID switch의 대부분이 ADS-B 공백 뒤(애틀랜타 117.6회)나 다른 표적 근접(시드니 42.1회)이라 IMM으로 줄지 않습니다. 애틀랜타는 항공기당 정답 구간 수가 1.60으로 가장 많습니다(스히폴 1.07).
- 예비 공항(마드리드, 덴버)은 추출만 하고 돌리지 않았습니다.

### Q5 (`tune_confirm.json`, `runs/EHAM_1106_eval__ekf__lam*_m*n*.json`)

- 사전 등록한 제약(기준 조건 λ 5에서 GOSPA가 3/4보다 5% 넘게 나빠지면 제외)에 걸려 더 엄격한 규칙이 모두 탈락했습니다(4/5가 +7.4%, 6/8이 +22.0%). 선택은 3/4 그대로입니다.
- 사전 등록 밖 탐색: 6/8은 λ 1000에서 가짜 항적을 555 → 8.3/scan, ID switch를 345 → 53회로 줄이지만, 기준 조건에서 시작 지연 13.8 → 30.4 s, 놓친 표적 0.82 → 1.90/scan, GOSPA 2,236 → 2,656 m입니다.

## 틀린 예측 (작성 에이전트의 예측)

| 예측 | 결과 | 맞음 |
|---|---|---|
| Q1 선회 비율 65% (50–80%) | 99.3% | 틀림(범위 밖, 낮게 봄) |
| Q1 기저율 15–25% | 19.3% | 맞음 |
| Q1 탐지 누락이 둘째 원인 10–20% | 0.4% (선회와 겹친 누락은 50건) | 틀림 |
| Q1 설명 안 됨 10% 미만 | 0.4% | 맞음 |
| Q2 잃음 13.3 → 7 이하 | 6.0 | 맞음 |
| Q2 전체 ID switch 17–20 | 15.4 | 틀림(더 줄었음) |
| Q2 다른 표적 근접 분류는 거의 그대로 | 4.6 → 2.5 | 틀림 |
| Q2 선회 구간 RMSE −20% | −11.3% | 틀림 |
| Q2 직선 구간 RMSE −5 ~ −10% | −1.5% | 틀림(등속 모형 q가 25로 선택됨) |
| Q2 실제 정답 NEES 3–5 | 2.67 | 틀림 |
| Q2 실행 시간 3–6배 | 1.39배 | 틀림 |
| Q3 filter 단계 일치 | 원점 좌표계 불일치(Stone Soup Jacobian), 양수 좌표계 일치 | 틀림 |
| Q3 비용을 맞추면 같은 답 | 3개 중 2개(나머지는 이 프로젝트의 6 km 한도) | 부분 |
| Q3 지표 차이 RMSE 1 m, ID switch ±2 이내 | 0.02 m, 0 | 맞음 |
| Q4 EKF > 기준선 전부 | 12/12 | 맞음 |
| Q4 기준선/EKF RMSE 비 2.5–3.5배 | 2.44–4.16배 | 틀림(범위 밖) |
| Q4 IMM 이득 3분의 2 이상 | 12/12 | 맞음 |
| Q4 히스로의 IMM 이득이 가장 큼 | 절대 감소량 최대(−25.9회) | 맞음 |
| Q4 히스로가 표적당 ID switch가 스히폴보다 많음 | 0.26 대 0.17 (시드니 0.94, 애틀랜타 0.61이 더 많음) | 맞음 |
| Q4 교통량 적은 곳은 구간이 0을 포함 | 오슬로 두 날 모두 0 아래 | 틀림 |
| Q5 5/6이 선택됨, λ 1000 가짜 항적 50 미만 | 3/4 유지 | 틀림 |

## 사전 등록과 다르게 된 점

1. **Q3 좌표계 추가**: filter 단계 불일치의 원인을 분리하려고 "모든 좌표가 양수인 좌표계" 대조를 추가했습니다. 등록에는 없던 실행입니다.
2. **Q3 추가 지표와 실행**: 항적 번호가 밀리면 등록한 "같은 번호 1 cm" 지표가 의미를 잃어, 번호와 무관한 위치 대응 비율을 추가했습니다. 6 km 한도를 12 km로 넓힌 대조(seed 3개)와 민감도 실행(시나리오 4개)도 추가했습니다.
3. **Q3 Stone Soup 기본 구성 미실행**: "가능하면"으로 적었던 Stone Soup 자체 시작기·삭제기 구성은 돌리지 않았습니다.
4. **6 km 한도는 고치지 않음**: 평가 결과를 본 뒤라 동결한 코드를 바꾸지 않았습니다. 본문 수치는 6 km 그대로이고, 12 km 결과를 따로 남겼습니다.
5. **Q5 탐색 실행**: 선택된 규칙이 3/4 그대로라 비교할 것이 없어, 제약 없이 가장 좋았던 6/8을 "사전 등록 밖 탐색"으로 표시해 평가했습니다.
6. **Q1 추가 열**: 사건 표에 속력을 넣고 표적별 집중도를 계산했습니다. 분류 규칙은 바꾸지 않았습니다.
7. **실행 시간**: 평가 실행 때 다른 작업과 겹친 run이 있어, 실행 시간은 다른 작업이 없을 때 따로 쟀습니다(`timing.json`).
8. **재실행 2건**: (a) Q3 첫 실행은 filter 불일치를 보고 중단했고, 그때 남은 프로세스가 결과 파일에 함께 쓰고 있어 모두 지우고 다시 돌렸습니다. (b) 스히폴 평가 구간 EKF 결과 파일은 속력 열을 넣으려고 다시 만들었고, seed별 요약과 원인 수가 이전과 같은지 확인했습니다.
9. **시드니 시간대**: 가장 붐빈 5분이 23:25라 규칙대로 22:57–23:27로 밀었습니다.
10. **IMM 시험 1개 완화**: 제가 덧붙였던 "3°/s 합성 선회에서 ID switch 0회" 조건은 등록에 없던 것이고 20개 seed 중 2개에서 깨져, "EKF보다 적다"로 바꿨습니다(EKF는 20개 모두에서 잃음). 등록한 시험 조건은 조정 전·후 모두 통과했습니다.

## 전체 test 결과

32개 통과(1단계 20개 + IMM 6개 + 2단계 6개). 개인정보·식별자 검사는 유지하고 늘렸습니다(dbFlags 제외, 추출 열 목록, 추출 파일 열, 커밋된 결과 파일의 열 이름, 공항 목록이 한국 밖인지).

```text
============================= test session starts ==============================
platform darwin -- Python 3.12.8, pytest-9.2.0, pluggy-1.7.0 -- <project>/.venv/bin/python
cachedir: .pytest_cache
rootdir: <project>
configfile: pyproject.toml
testpaths: tests
collecting ... collected 32 items
tests/test_ekf_tracker.py::test_single_target_straight_line_converges PASSED [  3%]
tests/test_ekf_tracker.py::test_ekf_reduces_error_vs_raw_measurement PASSED [  6%]
tests/test_ekf_tracker.py::test_gate_threshold_and_mahalanobis PASSED    [  9%]
tests/test_ekf_tracker.py::test_gating_rejects_far_detection PASSED      [ 12%]
tests/test_ekf_tracker.py::test_hungarian_assignment_global_optimum PASSED [ 15%]
tests/test_ekf_tracker.py::test_m_of_n_confirmation_and_deletion PASSED  [ 18%]
tests/test_ekf_tracker.py::test_track_ids_persist_and_are_not_reused PASSED [ 21%]
tests/test_ekf_tracker.py::test_componentwise_assignment_matches_dense_solve PASSED [ 25%]
tests/test_geo.py::test_azimuth_convention_clockwise_from_north PASSED   [ 28%]
tests/test_geo.py::test_polar_cartesian_round_trip PASSED                [ 31%]
tests/test_geo.py::test_wrap_pi PASSED                                   [ 34%]
tests/test_geo.py::test_polar_cov_cross_range PASSED                     [ 37%]
tests/test_geo.py::test_geodetic_enu_round_trip_and_scale PASSED         [ 40%]
tests/test_geo.py::test_velocity_rotation_meridian_convergence PASSED    [ 43%]
tests/test_imm.py::test_transition_matrix_is_a_markov_semigroup PASSED   [ 46%]
tests/test_imm.py::test_ct_predict_exact_circle_small_omega_and_jacobian PASSED [ 50%]
tests/test_imm.py::test_turn_is_detected_and_tracked_better_than_cv PASSED [ 53%]
tests/test_imm.py::test_straight_line_accuracy_not_worse_than_cv PASSED  [ 56%]
tests/test_imm.py::test_nees_on_model_matched_truth PASSED               [ 59%]
tests/test_imm.py::test_imm_single_target_management_like_ekf PASSED     [ 62%]
tests/test_metrics_repro.py::test_gospa_known_values PASSED              [ 65%]
tests/test_metrics_repro.py::test_same_seed_reproducible_and_different_seed_differs PASSED [ 68%]
tests/test_metrics_repro.py::test_clutter_rate_matches_lambda PASSED     [ 71%]
tests/test_metrics_repro.py::test_hermite_exact_for_constant_acceleration PASSED [ 75%]
tests/test_metrics_repro.py::test_anees_bounds_contain_dof PASSED        [ 78%]
tests/test_privacy.py::test_dbflags_exclusion PASSED                     [ 81%]
tests/test_stage2.py::test_extractor_writes_no_identifier_column PASSED  [ 84%]
tests/test_stage2.py::test_processed_point_files_hold_only_allowed_columns PASSED [ 87%]
tests/test_stage2.py::test_committed_outputs_carry_no_identifier_fields PASSED [ 90%]
tests/test_stage2.py::test_sites_are_outside_korea_and_extract_script_applies_dbflags PASSED [ 93%]
tests/test_stage2.py::test_truth_turn_rate_matches_the_known_manoeuvre PASSED [ 96%]
tests/test_stage2.py::test_lost_track_in_a_known_turn_is_classified_as_turn PASSED [100%]
============================== 32 passed in 5.46s ==============================
```

## 남은 문제

- **gate 앞 6 km 한도**: 12 km로 바꾸는 것이 맞습니다. 영향은 평균 ID switch 0.00회 수준이지만, 독립 구현과 완전히 같아지려면 필요합니다.
- **좁게 도는 느린 항공기**: IMM을 써도 run당 5.0회를 잃습니다(최대 선회율 중앙값 9.1°/s). 4.8초 간격으로는 한계가 있습니다.
- **IMM 조정이 격자 가장자리**: q_cv, 선회율 잡음, 두 체류 시간이 모두 격자의 가장 큰 값입니다. 격자 밖은 보지 않았습니다.
- **일관성**: 실제 정답 NEES가 2.67로 여전히 4보다 작습니다.
- **IMM의 독립 검증 없음**: Stone Soup과 대조한 것은 등속 EKF 추적기뿐입니다. IMM은 합성 정답 시험만 했습니다.
- **항적 관리의 독립 검증 없음**: Stone Soup 대조에서 시작·확정·삭제는 같은 규칙을 다시 쓴 코드입니다.
- **고밀도 클러터**: 확정 규칙만으로는 기준 조건과 고밀도를 함께 만족하지 못했습니다. JPDA·MHT는 설계 메모만 있습니다.
- **ADS-B 공백**: 애틀랜타에서 ID switch의 64%가 정답 공백 뒤입니다. 추적기가 아니라 정답 자료의 한계입니다.
- **표본**: 이틀, 공항 6곳, 모두 ADS-B 수신이 좋은 지역입니다.
- **디스크**: 둘째 날 원본 3.4 GiB를 `data/raw/adsblol_2026-11-11`에 남겨 두었습니다(git 제외). 디스크 여유는 26 GiB입니다. 필요 없으면 지워도 되고, 추출 파일(`data/processed/sites/`)만 있으면 2단계를 다시 돌릴 수 있습니다.
- **브랜치**: 이미 push된 브랜치라 최신 main 위로 rebase하지 않았습니다(강제 push가 필요해짐).

## 공개 저장소·사이트에 반영할 변경 목록 (이번에는 하지 않음)

공개 저장소 hyh4867/radar-track-lab:
- 2단계 코드(`imm.py`, `diagnose.py`, `scenarios.py`, 2단계 스크립트, test 12개), `configs/stage2.yaml`, `configs/sites.yaml`.
- `results/data/stage2/`(9.8 MB)와 그림 4장. 용량이 부담이면 `runs/`의 사건 목록을 빼고 요약만 올릴 수 있습니다.
- 영어 README를 2단계 기준으로 다시 쓰기: 요약 문단, IMM 결과 표, Q4 표, Stone Soup 대조, 한계.
- `docs/PREREGISTRATION_2.md`는 한국어입니다. 올릴지와 번역할지 결정이 필요합니다. `docs/reports/`는 지금까지처럼 올리지 않는 것을 권합니다.

포트폴리오 사이트의 Radar Track Lab 항목:
- 대표 수치에 IMM 추가: 위치 RMSE 528 / 175 / 168 m, ID switch 459.2 / 24.9 / 15.4회.
- "다른 공항 5곳과 둘째 날, 유효 시나리오 12개 모두에서 유지" 한 줄과 시나리오 그림.
- 검증 문단: 공개 라이브러리 대조에서 찾은 두 가지(Stone Soup의 수치 Jacobian, 이 프로젝트의 6 km 한도).
- 한계 문단: "선회 원인을 확인하지 않았다"를 Q1 결과로 교체.

웹 데모(바꾸지 않았고, 바꾼다면):
- EKF와 IMM 전환 토글, 또는 IMM 시나리오 추가.
- 다른 공항 시나리오 추가(데이터 파일이 늘어남).
- 옆 패널의 기준선 비교에 IMM 값 추가.
- 썸네일은 그대로 써도 됩니다(화면 구성이 같음).

그 밖에: Stone Soup의 Jacobian 문제는 상류 저장소에 알릴 만한 내용입니다. 외부에 글을 올리는 일이라 하지 않았고, 원하면 재현 코드와 함께 초안을 쓰겠습니다.

## commit hash

- `12d2a1b` 사전 등록 (실행 전)
- `af45ee2` IMM·진단·추출 코드, 조정 결과, 매개변수 동결 (평가 전)
- `51df627` Q1·Q2·Q4 평가 실행 결과, 집계, 그림, test
- `50b2c6f` Stone Soup 대조, Q5, README와 RESULTS.md 생성
- 이 보고서: 이 파일을 담은 커밋
