# 2026-11-20 Radar Track Lab 3단계 보고서: 평가 감사

브랜치 `hyh4867/Radar`, `projects/radar-track-lab` 안에서만 작업했습니다. main 병합, 공개 저장소, 데모 재배포, 사이트 변경은 하지 않았습니다. 기존 결과 파일(`results/data/`, `results/RESULTS.md`)과 데모 자료(`web/`, `results/thumbnails/`)는 바꾸지 않았고, 새 산출물은 `results/audit/`에 있습니다. 민간 항공기만 쓰고 식별자는 저장하지 않았습니다.

## 결론

| 질문 | 답 | 출처 |
|---|---|---|
| A1. 짝 차이는 얼마이고 기준값과 맞는가 | 확인용 기준값 세 개가 소수 둘째 자리까지 재현됨. seed 집합 오류 0건 | `results/audit/paired_reference_check.json` |
| A2. 공통 표본에서 두 RMSE 차이는 어떻게 바뀌는가 | 거의 그대로. scan-end −353.41 → −353.93 m, update-time −47.02 → −47.58 m | `results/audit/sample_audit.md` |
| A3. README 문장은 유지되는가 | 판정 "유지". 단, "항적 번호 유지" 부분은 RMSE로는 확인되지 않아 단서를 붙임 | `results/audit/sample_audit.json` |
| A4. 다른 공항·시간대에서도 방향이 같은가 | 표본 밖 유효 시나리오 12개 모두 같은 방향, 모두 "유지" | 같은 파일 |

## 한 일

1. **프로토콜**: `docs/AUDIT_PROTOCOL.md`를 새 계산 전에 커밋했습니다(`3be6698`). 질문, 코드로 확인한 표본 규칙, 키, 지표 정의, seed, 판정 규칙, 이미 본 결과를 적었습니다.
2. **짝 표**: `scripts/audit_paired.py`(기존 CSV/JSON만 읽음, 약 1초)가 스윕 24개 조건과 2단계 시나리오 15개에서 seed로 짝지은 차이를 만듭니다. EKF − 기준선, IMM − EKF, IMM − 기준선, 지표 10개, 모두 690행입니다.
3. **표본 기록**: `sim.run(..., audit=True)`로 두 RMSE의 표본을 기록하는 선택형 경로를 넣었습니다(표본 키, 시각, 제곱 오차, 제외 이유). 기본값에서는 점수가 바뀌지 않습니다.
4. **공통 표본 분석**: 시나리오 15개 × 방법 2개 × seed 20개를 기록을 켜고 다시 돌렸습니다. 실행마다 점수가 2단계 결과 파일과 같은지 검사했고 모두 같았습니다.
5. **fixture test**: 손으로 계산한 답과 비교하는 test 8개를 추가했습니다.
6. **면접 준비**: `docs/INTERVIEW.md`(한국어·영어 90초 답변, 꼬리 질문 4개, 누가 무엇을 정했는지 표).
7. README에 "평가 감사" 절을 추가했습니다(수치는 `scripts/audit_report.py`가 생성).

## 두 RMSE가 쓰는 표본 (코드 확인: `src/radar_track_lab/sim.py`, `metrics.py`)

| | scan-end RMSE | update-time RMSE |
|---|---|---|
| 시각 | scan이 끝나는 시각(모든 표적 공통) | 탐지마다 다른 조사 시각 |
| 추정 상태 | 확정 항적을 그 시각으로 예측한 위치(기준선은 마지막 탐지점) | 탐지로 갱신한 직후의 위치(기준선은 탐지점 그 자체) |
| 정답 연결 | 전체 표적과 확정 항적의 GOSPA 최적 배정에서 2 km 안인 쌍 | 그 탐지를 만든 표적(배정을 거치지 않음) |
| 워밍업 | 평가 시각이 시작 + 60 s 이후 | 탐지 시각이 시작 + 60 s 이후 |
| 빠지는 것 | 2 km 안에 짝이 없는 표적과 항적 | 가항적의 갱신, 클러터로 갱신된 경우, 탐지가 없거나 연관되지 않은 경우 |

## 결과 수치 (스히폴 평가 구간, 기준 조건, seed 20개)

짝 차이는 EKF − 기준선, 평균 [95% t-구간]입니다. 이 구간은 정답 궤적이 고정된 한 교통 구간에서 탐지 잡음·누락·클러터만 바꾼 시뮬레이션 변동입니다. 다른 날·다른 공항에 대한 불확실성은 들어 있지 않습니다.

### 짝 차이 (`results/audit/paired_effects.md`)

| 지표 | 짝 차이 | 퍼센트 감소 |
|---|---:|---:|
| scan-end RMSE [m] | −353.41 [−355.13, −351.70] | 66.9% |
| update-time RMSE [m] | −47.02 [−47.56, −46.49] | 27.2% |
| ID switch (30분) | −434.25 [−442.45, −426.05] | 94.6% |
| 항적 끊김 | −410.6 [−418.4, −402.7] | |
| 놓친 표적 / scan | −3.19 [−3.26, −3.13] | |
| 가짜 항적 / scan | −3.84 [−3.90, −3.77] | |
| GOSPA [m] | −3,272 [−3,301, −3,243] | |
| ├ 위치 항 | −2,364 [−2,374, −2,354] | |
| ├ 놓친 표적 항 | −1,552 [−1,577, −1,526] | |
| └ 가짜 항적 항 | −1,666 [−1,689, −1,644] | |

- 퍼센트 감소 = 100 × (기준선 평균 − EKF 평균) / 기준선 평균. 분모는 기준선의 seed 평균입니다.
- 스윕 24개 조건 전부에서 scan-end RMSE, update-time RMSE, ID switch의 짝 차이 구간이 0 아래입니다. 조건별 값은 표 파일에 있습니다.

### 표본 감사 (`results/audit/sample_audit.md`)

| RMSE | 표본 | run당 표본 수 (EKF / 기준선) | EKF [m] | 기준선 [m] | 짝 차이 [m] |
|---|---|---:|---:|---:|---:|
| scan-end | 각자의 표본 | 17,958 / 16,799 | 174.7 | 528.1 | −353.41 [−355.13, −351.70] |
| scan-end | 공통 표본 | 16,788 | 174.2 | 528.2 | −353.93 [−355.64, −352.22] |
| update-time | 각자의 표본 | 16,047 / 14,780 | 125.8 | 172.8 | −47.02 [−47.56, −46.49] |
| update-time | 공통 표본 | 14,714 | 125.0 | 172.6 | −47.58 [−48.07, −47.09] |

- scan-end: 워밍업 뒤 표적-scan 18,256개 중 공통 16,788개(92.0%), EKF만 1,169개, 기준선만 10개, 둘 다 없음 288개. 공통 표본은 사실상 기준선의 표본과 같습니다.
- update-time: 표적 탐지 16,420개 중 공통 14,714개(89.6%), EKF만 1,334개, 기준선만 66개.
- 공통에서 빠진 표본이 특별히 어려운 것은 아니었습니다. 기준선이 짝을 못 만든 1,169개에서 EKF의 RMSE는 180.9 m(공통 표본 174.2 m)입니다.
- 기준선의 scan-end 오차는 마지막 탐지 뒤 지난 시간에 따라 204 m(0–1.2초) → 617 m(3.6–4.8초)로 커집니다. EKF는 119 → 200 m입니다. 기술일 뿐이고 원인을 나눈 것은 아닙니다.

### README 문장의 판정

- 문장: "필터의 평활 효과는 이 정도이고, 위 표의 큰 차이는 scan 사이 예측과 항적 번호 유지에서 나옵니다."
- 프로토콜의 규칙으로 **유지**입니다. 공통 표본 scan-end 차이는 각자 표본 차이의 100.1%이고, update-time 차이보다 크며 두 구간이 겹치지 않습니다.
- **붙인 단서**: 공통 표본은 두 방법이 모두 따라간 표적-scan만 남기는데도 차이가 그대로입니다. 따라서 scan-end RMSE의 차이는 "항적 번호 유지" 때문이라고 할 수 없습니다. 번호 유지의 차이는 ID switch(24.9 대 459.2회), 끊김(3.6 대 414.2회), 놓친 표적(0.82 대 4.02/scan)에 나타납니다. 문장의 "예측" 부분은 관찰과 맞지만 직접 떼어 본 실험은 없습니다.
- 두 원래 RMSE로 원인별 퍼센트를 나누지 않았습니다.
- README의 원래 문장은 지우지 않고, 감사 절을 가리키는 괄호 한 줄을 덧붙였습니다.

### 다른 시나리오

| 시나리오 (UTC) | scan-end 차이, 각자 표본 | 공통 표본 | update-time 차이, 공통 표본 | 판정 |
|---|---:|---:|---:|---|
| 스히폴 11-06 14:40 | −351.0 | −351.7 | −45.7 | 유지 |
| 런던 히스로 11-06 | −350.2 | −351.7 | −38.5 | 유지 |
| 오슬로 11-06 | −361.9 | −364.4 | −35.2 | 유지 |
| 애틀랜타 11-06 | −321.8 | −323.4 | −48.2 | 유지 |
| 취리히 11-06 | −399.7 | −402.3 | −43.4 | 유지 |
| 시드니 11-06 | −230.1 | −231.4 | −31.5 | 유지 |
| 스히폴 11-11 | −408.8 | −411.3 | −43.1 | 유지 |
| 런던 히스로 11-11 | −368.7 | −371.0 | −38.3 | 유지 |
| 오슬로 11-11 | −441.3 | −445.1 | −40.2 | 유지 |
| 애틀랜타 11-11 | −304.3 | −306.8 | −46.9 | 유지 |
| 취리히 11-11 | −472.5 | −475.7 | −51.6 | 유지 |
| 시드니 11-11 | −262.7 | −265.1 | −34.6 | 유지 |

- 표본 밖 유효 시나리오 12개 중 12개에서 방향이 같습니다(두 차이 모두 음수, scan-end 쪽이 더 큼). 유효 기준 미달 2개(스히폴 02:00, 04:30)도 같은 방향이지만 비율에는 넣지 않았습니다.
- 구간을 포함한 전체 표는 `results/audit/sample_audit.md`에 있습니다.
- 예비 공항(마드리드, 덴버)은 2단계에서 돌리지 않았으므로 여기서도 뺐습니다.

## 그림

- `results/audit/figures/audit_paired_sweep.png`: 스윕 24개 조건의 짝 차이(scan-end, update-time)
- `results/audit/figures/audit_sample_accounting.png`: 두 RMSE가 쓰는 표본의 구성
- `results/audit/figures/audit_common_vs_original.png`: 시나리오별 각자 표본과 공통 표본의 짝 차이

## fixture test (손으로 계산한 답)

| test | 확인하는 것 |
|---|---|
| `test_update_common_sample_with_asynchronous_times_and_exclusions` | 탐지마다 다른 시각, 가항적·워밍업 제외, 공통 1개에서 RMSE 10과 15 |
| `test_scan_end_common_sample_drops_the_hard_pair_and_can_flip_the_comparison` | 한 방법만 따라간 어려운 짝(1,000 m)이 빠지면 비교가 뒤집힐 수 있음, 워밍업 행 제외 |
| `test_duplicate_and_mismatched_keys_are_errors` | 중복 키, 같은 키인데 정답이나 시각이 다른 경우, 표적-scan 목록이 다른 경우는 오류 |
| `test_paired_difference_and_percent_reduction_by_hand` | 짝 차이 평균, t-구간 반폭, 퍼센트 감소의 분모 |
| `test_unpaired_target_is_excluded_from_the_scan_end_sample` | 2 km 밖 추정은 짝이 아니고 놓친 표적과 가짜 항적으로 셈 |
| `test_recording_does_not_change_scores_and_reproduces_both_rmses` (EKF, 기준선, IMM) | 기록을 켜도 점수가 같음, 기록에서 두 RMSE를 다시 계산하면 같음, 시각 규칙 |

## 전체 test 출력

40개 통과(1단계 20개, 2단계 12개, 감사 8개).

```text
============================= test session starts ==============================
platform darwin -- Python 3.12.8, pytest-9.2.0, pluggy-1.7.0 -- <project>/.venv/bin/python
cachedir: .pytest_cache
rootdir: <project>
configfile: pyproject.toml
testpaths: tests
collecting ... collected 40 items
tests/test_audit.py::test_update_common_sample_with_asynchronous_times_and_exclusions PASSED [  2%]
tests/test_audit.py::test_scan_end_common_sample_drops_the_hard_pair_and_can_flip_the_comparison PASSED [  5%]
tests/test_audit.py::test_duplicate_and_mismatched_keys_are_errors PASSED [  7%]
tests/test_audit.py::test_paired_difference_and_percent_reduction_by_hand PASSED [ 10%]
tests/test_audit.py::test_unpaired_target_is_excluded_from_the_scan_end_sample PASSED [ 12%]
tests/test_audit.py::test_recording_does_not_change_scores_and_reproduces_both_rmses[ekf] PASSED [ 15%]
tests/test_audit.py::test_recording_does_not_change_scores_and_reproduces_both_rmses[nn] PASSED [ 17%]
tests/test_audit.py::test_recording_does_not_change_scores_and_reproduces_both_rmses[imm] PASSED [ 20%]
tests/test_ekf_tracker.py::test_single_target_straight_line_converges PASSED [ 22%]
tests/test_ekf_tracker.py::test_ekf_reduces_error_vs_raw_measurement PASSED [ 25%]
tests/test_ekf_tracker.py::test_gate_threshold_and_mahalanobis PASSED    [ 27%]
tests/test_ekf_tracker.py::test_gating_rejects_far_detection PASSED      [ 30%]
tests/test_ekf_tracker.py::test_hungarian_assignment_global_optimum PASSED [ 32%]
tests/test_ekf_tracker.py::test_m_of_n_confirmation_and_deletion PASSED  [ 35%]
tests/test_ekf_tracker.py::test_track_ids_persist_and_are_not_reused PASSED [ 37%]
tests/test_ekf_tracker.py::test_componentwise_assignment_matches_dense_solve PASSED [ 40%]
tests/test_geo.py::test_azimuth_convention_clockwise_from_north PASSED   [ 42%]
tests/test_geo.py::test_polar_cartesian_round_trip PASSED                [ 45%]
tests/test_geo.py::test_wrap_pi PASSED                                   [ 47%]
tests/test_geo.py::test_polar_cov_cross_range PASSED                     [ 50%]
tests/test_geo.py::test_geodetic_enu_round_trip_and_scale PASSED         [ 52%]
tests/test_geo.py::test_velocity_rotation_meridian_convergence PASSED    [ 55%]
tests/test_imm.py::test_transition_matrix_is_a_markov_semigroup PASSED   [ 57%]
tests/test_imm.py::test_ct_predict_exact_circle_small_omega_and_jacobian PASSED [ 60%]
tests/test_imm.py::test_turn_is_detected_and_tracked_better_than_cv PASSED [ 62%]
tests/test_imm.py::test_straight_line_accuracy_not_worse_than_cv PASSED  [ 65%]
tests/test_imm.py::test_nees_on_model_matched_truth PASSED               [ 67%]
tests/test_imm.py::test_imm_single_target_management_like_ekf PASSED     [ 70%]
tests/test_metrics_repro.py::test_gospa_known_values PASSED              [ 72%]
tests/test_metrics_repro.py::test_same_seed_reproducible_and_different_seed_differs PASSED [ 75%]
tests/test_metrics_repro.py::test_clutter_rate_matches_lambda PASSED     [ 77%]
tests/test_metrics_repro.py::test_hermite_exact_for_constant_acceleration PASSED [ 80%]
tests/test_metrics_repro.py::test_anees_bounds_contain_dof PASSED        [ 82%]
tests/test_privacy.py::test_dbflags_exclusion PASSED                     [ 85%]
tests/test_stage2.py::test_extractor_writes_no_identifier_column PASSED  [ 87%]
tests/test_stage2.py::test_processed_point_files_hold_only_allowed_columns PASSED [ 90%]
tests/test_stage2.py::test_committed_outputs_carry_no_identifier_fields PASSED [ 92%]
tests/test_stage2.py::test_sites_are_outside_korea_and_extract_script_applies_dbflags PASSED [ 95%]
tests/test_stage2.py::test_truth_turn_rate_matches_the_known_manoeuvre PASSED [ 97%]
tests/test_stage2.py::test_lost_track_in_a_known_turn_is_classified_as_turn PASSED [100%]
============================== 40 passed in 5.77s ==============================
```

## 실행한 명령

```sh
.venv/bin/python scripts/audit_paired.py      # 짝 표와 기준값 대조 (1.1초)
screen -dmS radar-audit bash -c 'caffeinate -i .venv/bin/python scripts/audit_samples.py > data/processed/audit.out 2>&1'
                                               # 표본 기록 실행. ps로 다른 세션 확인 뒤 하나만 실행
.venv/bin/python scripts/audit_report.py      # 판정, 표, 그림 3장, README 감사 블록
.venv/bin/python -m pytest -v                 # 40 passed
```

- `audit_samples.py`는 예비 공항 항목에서 한 번 멈췄습니다(2단계 결과 파일이 없음). 건너뛰도록 고쳐 나머지 6개 시나리오를 이어서 돌렸습니다. 이미 끝난 9개는 체크포인트에서 그대로 썼습니다.

## 프로토콜과 다르게 된 점

- 없음에 가깝습니다. 프로토콜에 "시나리오 15개"라고 적은 그대로이고, 예비 공항을 빼는 것도 2단계 규칙과 같습니다.
- 보조 기술(마지막 탐지 뒤 지난 시간별 RMSE)은 기준선 항적의 시간으로만 나눴습니다.
- 표본 단위 기록은 예시로 스히폴 평가 구간 seed 하나만 파일로 남겼습니다(`results/audit/samples_example/`, 4개, 합 1 MB). 나머지는 seed별 집계만 저장했습니다.

## 남은 문제

- "예측 때문에 차이가 난다"는 직접 분리한 적이 없습니다(아래 제안).
- 공통 표본 분석은 EKF 대 기준선만 했습니다. IMM 대 EKF는 짝 표에만 있습니다.
- 2단계에서 남긴 문제(6 km 한도, IMM 격자 가장자리, 고밀도 클러터)는 그대로입니다.
- 브랜치는 최신 main 위로 rebase하지 않았습니다(이미 push된 브랜치라 강제 push가 필요해짐).

## 다음 단계 제안 (하나)

**기준선에 예측만 붙인 변형을 같은 seed로 한 번 돌린다.**

- 내용: 기준선 항적에 최근 두 탐지의 차로 구한 속도를 주고, scan 끝 시각까지 직선으로 외삽합니다. 필터, gating, 연관 방식은 기준선 그대로입니다(연결 반경 2 km도 그대로).
- 답하려는 것: scan-end RMSE 차이 353 m 가운데 예측만으로 얼마나 줄어드는가. 지금은 관찰과 맞는 설명일 뿐입니다.
- 입력: 기존 스히폴 평가 구간, 같은 seed 20개, 기준 조건. 새 데이터와 조정이 필요 없습니다. 실행 시간은 1분 미만입니다.
- 규칙(실행 전에 적을 것): 지표는 scan-end RMSE(각자 표본과 공통 표본)와 ID switch의 짝 차이. 조정할 매개변수를 두지 않습니다.
- 중단 규칙: 기존 EKF와 기준선의 점수가 한 자리라도 달라지면 멈춥니다. 변형이 하나를 넘어가면(예: 연결 반경도 바꾸고 싶어지면) 멈추고 따로 요청을 받습니다.

## commit hash

- `3be6698` 감사 프로토콜 (계산 전)
- 감사 코드, 산출물, 면접 문서, 이 보고서: 이 파일을 담은 커밋
