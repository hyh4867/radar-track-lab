# Radar Track Lab 6단계: Mode C 고도로 다른 고도의 교차 항공기 구분하기(G1)와 적은 클러터의 바닥값

브랜치 `hyh4867/radar-stage6`(시작점 `hyh4867/radar-stage5` e57a618). 사전 등록은 `docs/PREREGISTRATION_6.md`다. 5단계 결과를 보고 세운 후속 실험이다.

## 세 줄 요약

1. **1부 판정: 부분 개선(네 항목 중 3·4만 만족). 사이트 한계 문구가 말하는 "다른 고도의 교차 항공기 구분"은 이번 방법으로 나아지지 않았다.**
   - 오차 없는 Mode C에서 H1+G1은 ID switch가 H1보다 적은 구간이 EKF 3/13, IMM 1/13이었다.
   - KATL_1106_peak의 "가까운 다른 항공기와 바뀜"(EKF)은 H1 38.05 → 42.55로 늘었다.
   - 교차 사건 바뀜 합(EKF, 13구간, run당)도 160.85 → 170.35로 늘었다.
2. 판정 4(Mode C 오차에서 11/13)를 만족한 이유는 교차 구분이 아니었다. 5단계 H1 자체가 Mode C 오차에 약했고, G1이 그 약점을 막았다.
   - 잘못된 고도 하나로 항적이 원뿔 안으로 판단돼 유지되고, 그 뒤 맞는 보고를 거절한다. ENGM_1106_peak에서 유지 항적-scan이 0 → 107/run이었다.
   - H1의 ID switch는 오차를 넣으면 13개 구간 모두 늘었다(EKF 1.08–2.70배).
3. 남은 문제:
   - 사후 분석에서 G1의 손해는 대부분 기준 궤적 고도가 몇 초 사이 ±400 ft 출렁이는 소수 항공기에서 나왔다(EHAM 5.4/5.4, YSSY 13.4/15.8 run당). 수직 속도 외삽이 한 번 빗나가면 고도 창이 다시 따라잡지 못하는 설계 결함이다.
   - **2부 판정: 부분 개선(규칙상)이지만 실질 변화는 없다.**
     - 데이터 바닥값(f = 0.25)은 GOSPA가 다섯 조건 모두 5단계와 1% 안에서 같다.
     - λ5 놓친 표적은 −0.001/scan, 확정 지연은 −0.02 s 줄었다.
     - JIPDA 대비 λ5 손해(놓친 표적 +0.29, 확정 +4.8 s)는 그대로다.
     - 사후 확인에서 바닥값을 낮춰 표적 보고 위치의 추정 밀도가 참값의 30배 → 3배로 줄었는데도 결과가 같았다. λ5 손해의 원인은 바닥값이 아니다.

## 1. 한 일

- `src/radar_track_lab/cone.py`
  - G1을 넣었다(`setup_cone_v2(..., gate_all=True)`). H1의 고도 확인 대상이 아닌 확정 항적 가운데 Mode C 기록이 있는 항적이 대상이다. Mode C가 있는 표적 보고는 예측 고도 ±Δh 안이어야 받는다. 식은 5단계 H1과 같다.
  - 고도가 없는 보고는 2차원 게이트만 쓴다. H1 대상(유지 중이거나 막 나온 항적)은 5단계 규칙 그대로 고도 없는 보고를 받지 않는다.
  - Mode C 오차 주입 `apply_modec_errors`를 넣었다. 누락 2%, 잘못된 값 1%(0–45,000 ft 균등, 100 ft 양자화)이고, 난수는 seed별로 따로 쓴다. **이 비율은 문헌 값이 아니라 가정값이다.**
- `src/radar_track_lab/crossing.py`: 교차 사건을 정의했다. 수평 2 km 안이고 고도 차가 1,000 ft 이상인 연속 scan이다. 교차 사건 바뀜은 사건 ±3 scan과 겹치는 ID switch다.
- 2부용 `AdaptiveClutterMapDensity(floor_frac=…)`를 넣었다. 기본값 None이면 5단계와 같다.
- 단위 시험 9개를 추가했다. `tests/test_stage6_g1.py` 5개, `tests/test_stage6_floor.py` 4개다.
- 퇴행 확인:
  - seed 2개: M4, H1(EHAM·KATL, EKF·IMM)과 5단계 JIPDA-amap(lam200_map) 9개 파일이 모두 같았다(`results/stage6/regression.json`).
  - 1부 본 실행의 M4와 H1 전체(13구간 × EKF·IMM × seed 20 = 1,040 run의 summary 전체와 ID switch·misses 잃음)도 5단계 파일과 모두 같았다(`results/stage6/regression_full.json`).
- 1부 실행: 13개 구간 × EKF·IMM × seed 20. 오차 없음 M4/H1/H1+G1과 오차 있음 H1/H1+G1이다(20:31–21:01, 두 프로세스).

## 2. 1부 결과

출처: `results/stage6/cone_summary.md`, `results/stage6/cone_summary.json`, 실행 파일 `results/stage6/cone/`.

### 2.1 판정: 부분 개선

| 항목 | 기준 | 실제 | 결과 |
|---|---|---|---|
| 1 ID switch < H1 | EKF·IMM 각각 13개 중 11개 이상 | EKF 3/13, IMM 1/13 | 불만족 |
| 2 KATL_1106_peak near_other(EKF) | < M4 29.20 | 42.55(H1 38.05) | 불만족 |
| 3 가짜 항적 | 26개 모두 ≤ 1.10 × H1 | 최대 1.067(YSSY_1106_peak EKF) | 만족 |
| 4 오차 있을 때 EKF ID switch < H1 | 13개 중 9개 이상 | 11/13 | 만족(이유는 2.4절) |

- M4는 이번 새 실행 값이다. 5단계 29.20과 같다.
- 항목 1에서 "적음"이 아닌 구간 10개(EKF)의 내역: 7개는 H1보다 많다. 3개(ENGM 2개, LSZH_1111_same)는 H1과 정확히 같다.

### 2.2 오차 없는 Mode C: 주요 구간 (ID switch seed 평균, [ ]는 짝 t-구간)

| 구간 | 방법 | M4 | H1 | H1+G1 | G1 − H1 | near_other H1 → G1 | 교차 사건 바뀜 H1 → G1 |
|---|---|---:|---:|---:|---:|---:|---:|
| EHAM_1106_eval | EKF | 36.15 | 29.25 | 34.50 | +5.25 [+3.98, +6.52] | 4.75 → 6.00 | 6.70 → 6.90 |
| EHAM_1106_eval | IMM | 28.30 | 20.95 | 27.05 | +6.10 [+4.93, +7.27] | 3.60 → 4.90 | 4.60 → 5.05 |
| KATL_1106_peak | EKF | 210.80 | 200.25 | 204.05 | +3.80 [+0.54, +7.06] | 38.05 → 42.55 | 54.20 → 58.15 |
| KATL_1106_peak | IMM | 196.80 | 185.50 | 189.85 | +4.35 [+1.61, +7.09] | 37.60 → 42.65 | 53.35 → 57.90 |
| YSSY_1106_peak | EKF | 108.10 | 105.85 | 117.20 | +11.35 [+9.30, +13.40] | 50.75 → 60.30 | 23.20 → 31.05 |
| EGLL_1106_peak | EKF | 77.60 | 69.35 | 68.70 | −0.65 [−2.33, +1.03] | 7.00 → 6.10 | 10.60 → 8.90 |
| EHAM_1111_same | EKF | 12.70 | 10.65 | 10.20 | −0.45 [−1.15, +0.25] | 1.20 → 0.75 | 1.50 → 0.75 |

- 나머지 구간은 `cone_summary.md`에 있다.
- 교차 사건은 13개 구간에 모두 1,035개 있다(seed와 무관한 기준 궤적 성질). KATL_1106_peak 288개, EGLL_1106_peak 160개, ENGM_1111_same 0개다.
- 교차 사건 바뀜 합(13구간, run당): EKF는 M4 198.80, H1 160.85, H1+G1 170.35다. IMM은 190.05, 151.25, 162.50이다.
  - H1이 M4보다 줄인 몫은 대부분 원뿔 근처 사건이다.
  - G1은 EGLL·EHAM_1111_same에서 조금 줄이고 YSSY_1106_peak(+7.85)·KATL_1106_peak(+3.95)에서 늘렸다.
- 부작용(G1 − H1):
  - 가짜 항적은 거의 같다(비 0.995–1.067).
  - GOSPA는 YSSY_1106_peak EKF +38.0 m, EHAM_1106_eval +14.9 m이고, KATL 두 구간은 −5 – −11 m다.

### 2.3 사후 분석: G1이 무엇을 거절했나 (사전 등록 밖, 판정을 바꾸지 않음)

`scripts/stage6_g1_diag.py` → `results/stage6/g1_diag.json`, `scripts/stage6_g1_attrib.py` → `results/stage6/g1_attrib.json`. EKF, seed 5개다.

| 구간 | G1 거절 쌍 /run | 그중 "그 항적이 따라가던 항공기 자신의 보고" | G1 − H1 ID switch /run | 그중 고도 변화율 > 120 ft/s인 항공기 몫 |
|---|---:|---:|---:|---:|
| EHAM_1106_eval | 37.8 | 55% | +5.4 | +5.4(항공기 1대) |
| YSSY_1106_peak | 89.6 | 44% | +15.8 | +13.4(항공기 1대) |
| KATL_1106_peak | 166.4 | 0% | −1.0 | 0 |

- 자기 보고를 거절한 경우의 내역: 예측 고도와의 차이 중앙값 약 900 ft, 경과 시간 중앙값 9.6 s(한 scan을 놓친 뒤)다.
- 한 사례(EHAM, 항공기 2233): 기준 궤적 고도가 2,475 → 3,258 → 2,379 → 3,224 ft처럼 15–20 s마다 ±400 ft 출렁인다. 수직 속도가 83 ft/s로 추정된 직후 하강으로 바뀌자 예측은 위로 계속 가고, 창은 초당 50 ft만 넓어져 다시 따라잡지 못했다. 그러면 항적이 보고를 계속 거절하다 지워지고 새 번호가 붙는다.
- 이 출렁임이 실제 비행인지 ADS-B 원자료의 오류인지는 확인하지 않았다.
- **설계 결함**: 예측 고도가 창보다 빨리 멀어질 수 있다(|v_z| 최대 100 ft/s > 창 확장 50 ft/s). 한 번 빗나가면 회복할 길이 없다. 5단계 H1에서는 대상이 원뿔 근처로 좁아서 드러나지 않았다.
- **KATL에서 줄지 않은 이유**: G1은 다른 항공기의 보고를 거절했다(거절 쌍 166/run, 100%가 다른 항공기). 그래도 near_other와 교차 사건 바뀜은 늘었다. 원인은 분석하지 않았다. 고도가 1,000 ft 넘게 다른 교차 중에도 바뀜이 생기는 경로가 거절과 다른 곳(새 항적 시작, 미확정 항적, 2차원 게이트만 쓰는 고도 없는 보고)에 있을 수 있다.

### 2.4 Mode C 오차를 넣었을 때 (R)

| 구간(EKF) | H1 | H1(오차) | H1+G1(오차) | 유지 항적-scan /run H1 → H1(오차) |
|---|---:|---:|---:|---:|
| ENGM_1106_peak | 8.55 | 12.35 | 9.40 | 0 → 107 |
| LSZH_1111_same | 11.30 | 26.60 | 13.00 | 111 → 375 |
| KATL_1111_same | 179.70 | 200.90 | 188.75 | 290 → 625 |
| KATL_1106_peak | 200.25 | 215.60 | 214.15 | – |

- H1은 오차에 약하다. 13개 구간 모두 ID switch가 늘었다(EKF 1.08–2.70배). 가짜 항적은 1.16–2.25배 늘었다.
- 경로: 잘못된 고도(예: 40,000 ft) 하나가 항적의 마지막 Mode C가 된다. 그러면 원뿔 판단에서 원뿔 안으로 보여 유지되고, H1 고도 확인이 그 뒤 맞는 보고를 거절한다. ENGM_1106_peak에는 원뿔 효과가 없는데도 유지가 0 → 107/run 생겼다.
- G1은 잘못된 고도가 기록에 들어가는 것을 창 밖으로 막는다. 그래서 오차가 있으면 H1+G1이 H1보다 낫다(11/13). 사전 등록의 판정 4는 "오차에도 G1의 교차 구분 이득이 남는지"를 보려던 항목이다. 오차 없는 조건에서 G1 이득이 음수라서 그 질문에는 답이 되지 않는다.
- 사전 등록한 "이득이 남는 비율" Σ(H1_err − G1_err) / Σ(H1 − G1)은 EKF 54.00 / −23.60, IMM 53.50 / −26.25로 분모가 음수라 뜻이 없다.
- **5단계 보고 정정**: 5단계 보고서는 H1이 오차 없는 Mode C 덕분에 "실제보다 유리한 조건"이라고만 적었다. 이번 결과로 보면 오차가 있을 때 H1은 M4보다도 나빠질 수 있다. 예: ENGM_1106_peak 12.35 vs M4 8.55, LSZH_1111_same 26.60 vs M4 17.65.

### 2.5 예측 대 실제 (1부)

| 항목 | 에이전트 예측 | 검수자 예측 | 실제 |
|---|---|---|---|
| KATL_1106_peak near_other(EKF), H1 38.05 → | 34 (28–38) | 15 (8–24) | **42.55** (두 범위 밖, 위) |
| KATL_1106_peak ID switch(EKF), H1 200.25 대비 | −3 (−8 – +2) | −10 (−4 – −20) | **+3.80** (두 범위 밖) |
| 교차 사건 바뀜, H1 대비 | −50% (−20 – −80%) | −70% (−40 – −90%) | **EKF 합 +5.9%** (160.85 → 170.35) |
| 오차에서 G1 이득 | 80% 남음 | 30% 이내로 줄어듦 | 오차 없는 이득이 음수라 비교 불가. 오차가 있으면 G1이 H1보다 나음(H1의 약점 때문) |
| 판정 | 개선 20%, 부분 70%, 없음 10% | – | **부분 개선**(3·4만) |

- 두 예측 모두 G1이 교차 바뀜을 줄일 것으로 보았지만 틀렸다.
- 에이전트는 1부 사전 등록 1절의 조정 구간 동작 확인(H1 12 → G1 13)을 보고도 효과를 줄이기만 했고, 방향은 바꾸지 않았다.

## 3. 사전 등록과 달라진 점, 실행 세부

- 사후 분석 2개(2.3절)와 H1 오차 경로 확인(2.4절)은 사전 등록에 없던 것이다. 판정에는 쓰지 않았다.
- 메모리: 1부에서는 대기가 없었다(스왑 약 2.0 GB, 여유 70% 이상). 2부 조정 직전(21:08)에는 스왑이 3,122 MB라 규칙대로 5분 기다렸다. 이 시간에 다른 세션의 학습 프로세스는 보이지 않았다.
- 2부 후보 셋이 사실상 하나였다(7.1절). 사전 등록 12절에 실행 직후 적었다.
- 실행 로그(`results/stage6/logs/`)는 `.gitignore` 대상이라 커밋하지 않았다.

## 4. 테스트

`.venv/bin/python -m pytest -v`, 21:06 KST, 1부 실행 뒤: **104 passed in 45.59s**. 실패와 건너뜀은 없다. 5단계 95개에 이번 9개를 더한 수다. 2부 실행 뒤 21:50에 `-q`로 다시 돌린 결과도 **104 passed in 42.23s**다(그 사이에는 스크립트만 추가됨). 전체 출력(로컬 경로는 `<project>`로 바꿈):

```
============================= test session starts ==============================
platform darwin -- Python 3.12.8, pytest-9.2.0, pluggy-1.7.0 -- <project>/.venv/bin/python
cachedir: .pytest_cache
rootdir: <project>
configfile: pyproject.toml
testpaths: tests
collecting ... collected 104 items

tests/test_audit.py::test_update_common_sample_with_asynchronous_times_and_exclusions PASSED [  0%]
tests/test_audit.py::test_scan_end_common_sample_drops_the_hard_pair_and_can_flip_the_comparison PASSED [  1%]
tests/test_audit.py::test_duplicate_and_mismatched_keys_are_errors PASSED [  2%]
tests/test_audit.py::test_paired_difference_and_percent_reduction_by_hand PASSED [  3%]
tests/test_audit.py::test_unpaired_target_is_excluded_from_the_scan_end_sample PASSED [  4%]
tests/test_audit.py::test_recording_does_not_change_scores_and_reproduces_both_rmses[ekf] PASSED [  5%]
tests/test_audit.py::test_recording_does_not_change_scores_and_reproduces_both_rmses[nn] PASSED [  6%]
tests/test_audit.py::test_recording_does_not_change_scores_and_reproduces_both_rmses[imm] PASSED [  7%]
tests/test_audit.py::test_prediction_only_baseline_extrapolates_the_last_two_detections_by_hand PASSED [  8%]
tests/test_audit.py::test_prediction_only_baseline_shares_the_baseline_association_and_leaves_its_scores_alone PASSED [  9%]
tests/test_audit.py::test_three_way_common_scan_end_sample PASSED        [ 10%]
tests/test_audit.py::test_ekf_hold_output_reports_the_last_updated_position_and_shares_the_ekf_updates PASSED [ 11%]
tests/test_audit.py::test_ekf_hold_output_position_by_hand PASSED        [ 12%]
tests/test_ekf_tracker.py::test_single_target_straight_line_converges PASSED [ 13%]
tests/test_ekf_tracker.py::test_ekf_reduces_error_vs_raw_measurement PASSED [ 14%]
tests/test_ekf_tracker.py::test_gate_threshold_and_mahalanobis PASSED    [ 15%]
tests/test_ekf_tracker.py::test_gating_rejects_far_detection PASSED      [ 16%]
tests/test_ekf_tracker.py::test_hungarian_assignment_global_optimum PASSED [ 17%]
tests/test_ekf_tracker.py::test_m_of_n_confirmation_and_deletion PASSED  [ 18%]
tests/test_ekf_tracker.py::test_track_ids_persist_and_are_not_reused PASSED [ 19%]
tests/test_ekf_tracker.py::test_componentwise_assignment_matches_dense_solve PASSED [ 20%]
tests/test_geo.py::test_azimuth_convention_clockwise_from_north PASSED   [ 21%]
tests/test_geo.py::test_polar_cartesian_round_trip PASSED                [ 22%]
tests/test_geo.py::test_wrap_pi PASSED                                   [ 23%]
tests/test_geo.py::test_polar_cov_cross_range PASSED                     [ 24%]
tests/test_geo.py::test_geodetic_enu_round_trip_and_scale PASSED         [ 25%]
tests/test_geo.py::test_velocity_rotation_meridian_convergence PASSED    [ 25%]
tests/test_imm.py::test_transition_matrix_is_a_markov_semigroup PASSED   [ 26%]
tests/test_imm.py::test_ct_predict_exact_circle_small_omega_and_jacobian PASSED [ 27%]
tests/test_imm.py::test_turn_is_detected_and_tracked_better_than_cv PASSED [ 28%]
tests/test_imm.py::test_straight_line_accuracy_not_worse_than_cv PASSED  [ 29%]
tests/test_imm.py::test_nees_on_model_matched_truth PASSED               [ 30%]
tests/test_imm.py::test_imm_single_target_management_like_ekf PASSED     [ 31%]
tests/test_metrics_repro.py::test_gospa_known_values PASSED              [ 32%]
tests/test_metrics_repro.py::test_same_seed_reproducible_and_different_seed_differs PASSED [ 33%]
tests/test_metrics_repro.py::test_clutter_rate_matches_lambda PASSED     [ 34%]
tests/test_metrics_repro.py::test_hermite_exact_for_constant_acceleration PASSED [ 35%]
tests/test_metrics_repro.py::test_anees_bounds_contain_dof PASSED        [ 36%]
tests/test_privacy.py::test_dbflags_exclusion PASSED                     [ 37%]
tests/test_stage2.py::test_extractor_writes_no_identifier_column PASSED  [ 38%]
tests/test_stage2.py::test_processed_point_files_hold_only_allowed_columns PASSED [ 39%]
tests/test_stage2.py::test_committed_outputs_carry_no_identifier_fields PASSED [ 40%]
tests/test_stage2.py::test_sites_are_outside_korea_and_extract_script_applies_dbflags PASSED [ 41%]
tests/test_stage2.py::test_truth_turn_rate_matches_the_known_manoeuvre PASSED [ 42%]
tests/test_stage2.py::test_lost_track_in_a_known_turn_is_classified_as_turn PASSED [ 43%]
tests/test_stage3_c2_breakdown.py::test_breakdown_definitions PASSED     [ 44%]
tests/test_stage3_c2_breakdown.py::test_breakdown_rejects_inconsistent_events PASSED [ 45%]
tests/test_stage3_jpda.py::test_two_tracks_one_shared_detection_by_hand PASSED [ 46%]
tests/test_stage3_jpda.py::test_exact_matches_brute_force_and_lbp_is_close PASSED [ 47%]
tests/test_stage3_jpda.py::test_single_track_jipda_reduces_to_ipda PASSED [ 48%]
tests/test_stage3_jpda.py::test_pda_update_reduces_to_kalman_with_one_certain_detection PASSED [ 49%]
tests/test_stage3_jpda.py::test_grid_density_floor_and_average PASSED    [ 50%]
tests/test_stage3_jpda.py::test_trackers_follow_ncv_targets[jpda] PASSED [ 50%]
tests/test_stage3_jpda.py::test_trackers_follow_ncv_targets[jipda] PASSED [ 51%]
tests/test_stage3_jpda.py::test_jipda_rejects_dense_clutter_better_than_gnn PASSED [ 52%]
tests/test_stage3_jpda.py::test_jipda_with_certain_existence_equals_jpda PASSED [ 53%]
tests/test_stage3_pregate.py::test_adaptive_pregate_equals_no_pregate_ekf[5.0] PASSED [ 54%]
tests/test_stage3_pregate.py::test_adaptive_pregate_equals_no_pregate_ekf[200.0] PASSED [ 55%]
tests/test_stage3_pregate.py::test_adaptive_pregate_equals_no_pregate_imm PASSED [ 56%]
tests/test_stage3_pregate.py::test_pregate_radius_by_hand PASSED         [ 57%]
tests/test_stage3_pregate.py::test_fixed_6km_drops_a_gated_pair_that_adaptive_keeps PASSED [ 58%]
tests/test_stage3_sensor.py::test_swerling1_pd_by_hand PASSED            [ 59%]
tests/test_stage3_sensor.py::test_swerling1_matches_monte_carlo PASSED   [ 60%]
tests/test_stage3_sensor.py::test_calibration_by_hand PASSED             [ 61%]
tests/test_stage3_sensor.py::test_horizon_by_hand PASSED                 [ 62%]
tests/test_stage3_sensor.py::test_slant_and_elevation_against_vector_geometry PASSED [ 63%]
tests/test_stage3_sensor.py::test_slant_to_ground_round_trip_and_mode_c PASSED [ 64%]
tests/test_stage3_sensor.py::test_clutter_map_fractions_and_near_mean PASSED [ 65%]
tests/test_stage3_sensor.py::test_clutter_map_density_integrates_to_lambda_and_is_fixed_per_site PASSED [ 66%]
tests/test_stage3_sensor.py::test_merge_groups_by_hand PASSED            [ 67%]
tests/test_stage3_sensor.py::test_simulate_merge_reports_one_detection_at_the_mean PASSED [ 68%]
tests/test_stage3_sensor.py::test_simulate_cone_of_silence_and_slant_correction PASSED [ 69%]
tests/test_stage3_sensor.py::test_all_elements_off_reproduces_the_stage_1_model PASSED [ 70%]
tests/test_stage4_clutter_map.py::test_cell_boundaries PASSED            [ 71%]
tests/test_stage4_clutter_map.py::test_exponential_forgetting_arithmetic PASSED [ 72%]
tests/test_stage4_clutter_map.py::test_floor_is_jipda_est_floor_density PASSED [ 73%]
tests/test_stage4_clutter_map.py::test_converges_to_true_map_density[1000.0-1.5-30.0] PASSED [ 74%]
tests/test_stage4_clutter_map.py::test_converges_to_true_map_density[2000.0-3.0-100.0] PASSED [ 75%]
tests/test_stage4_clutter_map.py::test_uniform_clutter_matches_uniform_density PASSED [ 75%]
tests/test_stage4_cone.py::test_hold_time_formula PASSED                 [ 76%]
tests/test_stage4_cone.py::test_with_modec_attaches_quantised_altitude_to_target_reports_only PASSED [ 77%]
tests/test_stage4_cone.py::test_track_held_through_cone_and_not_deleted PASSED [ 78%]
tests/test_stage4_cone.py::test_hold_expires_after_t_max PASSED          [ 79%]
tests/test_stage5_amap.py::test_cap_half_widths PASSED                   [ 80%]
tests/test_stage5_amap.py::test_widening_stops_at_n_min PASSED           [ 81%]
tests/test_stage5_amap.py::test_cap_used_when_short_and_floor_kept PASSED [ 82%]
tests/test_stage5_amap.py::test_azimuth_wraps_and_range_edge_is_cut PASSED [ 83%]
tests/test_stage5_amap.py::test_box_sums_match_brute_force PASSED        [ 84%]
tests/test_stage5_amap.py::test_uniform_synthetic_clutter_converges_to_truth PASSED [ 85%]
tests/test_stage5_cone_v2.py::test_window_constants PASSED               [ 86%]
tests/test_stage5_cone_v2.py::test_vz_estimate_fit_clip_and_short_history PASSED [ 87%]
tests/test_stage5_cone_v2.py::test_alt_gate PASSED                       [ 88%]
tests/test_stage5_cone_v2.py::test_h1_holds_through_cone_like_stage4 PASSED [ 89%]
tests/test_stage5_cone_v2.py::test_h1_gate_rejects_other_altitude_and_clutter PASSED [ 90%]
tests/test_stage5_cone_v2.py::test_h2_extrapolates_altitude_for_cone_entry PASSED [ 91%]
tests/test_stage6_floor.py::test_floor_none_is_stage5 PASSED             [ 92%]
tests/test_stage6_floor.py::test_empty_map_uses_absolute_minimum PASSED  [ 93%]
tests/test_stage6_floor.py::test_floor_is_fraction_of_cap_window PASSED  [ 94%]
tests/test_stage6_floor.py::test_low_uniform_clutter_tracks_truth_not_fixed_floor PASSED [ 95%]
tests/test_stage6_g1.py::test_g1_gates_confirmed_tracks_with_history_only PASSED [ 96%]
tests/test_stage6_g1.py::test_g1_keeps_h1_rule_for_held_tracks PASSED    [ 97%]
tests/test_stage6_g1.py::test_g1_uses_vertical_speed PASSED              [ 98%]
tests/test_stage6_g1.py::test_modec_errors_rates_and_stream PASSED       [ 99%]
tests/test_stage6_g1.py::test_crossing_event_detection PASSED            [100%]

============================= 104 passed in 45.59s =============================
```

## 5. 남은 문제 (1부)

- **G1 설계 결함**: 예측 고도가 창보다 빨리 멀어지면 회복하지 못한다. 고칠 방법은 시험하지 않았다. 예를 들어 오래된 기록이면 v_z를 0으로 두거나, 거절이 이어지면 기록을 비우는 방법이 있다.
- **교차 구분 실패의 원인 미확인**: KATL에서 G1이 다른 항공기 보고를 거절하는데도 교차 사건 바뀜이 늘었다. 새 항적 시작, 미확정 항적, 고도 없는 보고의 2차원 연관 중 어디서 생기는지 보지 않았다.
- **H1의 Mode C 오차 취약성**: 5단계 원뿔 유지는 잘못된 고도 하나로 크게 나빠진다. 원뿔 판단에 쓰는 고도를 확인하는 장치가 필요하다.
- **기준 궤적 고도 출렁임**: 일부 항공기(EHAM 2233, YSSY 407)의 고도 변화율이 120 ft/s를 넘는다. 원자료 오류인지 확인하지 않았다.
- Mode C 오차율(2%, 1%)은 가정값이다.

## 6. 사이트 문구 제안 (반영하지 않음)

현재 한계 문구는 바꾸지 않을 것을 제안한다. "추적기는 2차원 위치를 사용하므로 서로 다른 고도에서 경로가 교차하는 항공기를 구분하지 못합니다."는 이번 결과와도 맞다. 덧붙인다면 다음을 제안한다.

"Mode C 고도를 모든 연관에 쓰는 시도도 해 보았지만, 이 시뮬레이션에서는 교차 지점의 번호 바뀜이 줄지 않았습니다(13개 구간 합 +6%). 고도 예측이 빗나간 항공기를 놓치는 문제가 새로 생겼습니다."

## 7. [2부] 데이터로 정하는 바닥값 (JIPDA-amap, 스히폴 평가 구간, M0, seed 20개)

출처: `results/stage6/summary.md`, `results/stage6/summary.json`, `results/stage6/tune_selection.json`, 실행 파일 `results/stage6/eval/`, 비교 대상 `results/stage5/eval/`, `results/stage3/b1/`. 1부 보고서 push(21:08, 9cb6976) 뒤에 시작해 21:44에 끝났다.

### 7.1 선택: 후보가 사실상 하나였다
- 조정 구간 점수(두 조건 GOSPA / JIPDA 중 큰 값)가 f = 0.25, 0.5, 1.0 모두 1.0669였다. 5단계 고정 바닥값은 1.0664다. f = 0.25와 0.5는 seed별 값까지 같았다.
- 이유: n_min 20에서 λ5의 거의 모든 칸이 상한 창 값을 쓴다. 그 칸의 바닥값 f × 상한 창 값은 f ≤ 1이면 밀도보다 클 수 없다. 실제로 바뀐 것은 "고정 바닥값 FLOOR → 절대 하한 FLOOR/10"뿐이었다.
- 사전 등록을 쓸 때 알아차렸어야 했다. 동점 규칙대로 f = 0.25를 동결했다.

### 7.2 판정: 부분 개선 (규칙상), 실질 변화 없음

| 조건 | GOSPA 비 (새 / 5단계) | 놓친 표적 짝 차이 | 확정 지연 짝 차이 (s) |
|---|---:|---:|---:|
| lam1000_map | 0.9942 | +0.030 [+0.009, +0.050] | −0.03 [−0.63, +0.56] |
| lam1000_uniform | 1.0002 | +0.002 [−0.002, +0.007] | +0.04 [−0.04, +0.11] |
| lam200_map | 1.0000 | +0.000 | +0.00 |
| lam5_map | 0.9999 | −0.001 [−0.002, −0.000] | −0.018 [−0.030, −0.006] |
| lam5_uniform | 0.9999 | −0.002 [−0.004, +0.000] | −0.021 [−0.037, −0.004] |

- (a) 다섯 조건 GOSPA 비 ≤ 1.01: 만족
- (b) λ5 두 조건의 놓친 표적과 확정 지연이 모두 줄어듦(상한 < 0): lam5_uniform 놓친 표적의 상한이 0을 넘어 불만족
- 줄어든 양은 놓친 표적 0.001–0.002/scan, 확정 0.02 s다. JIPDA 대비 손해(lam5_map 놓친 표적 +0.29, 확정 +4.8 s)와 비교하면 무시할 크기다.
- lam1000_map에서는 가짜 항적이 4.38 → 4.26, GOSPA가 −23 m [−33, −13]로 조금 나아졌고, 놓친 표적은 +0.03 늘었다.

### 7.3 사후 확인: λ5 손해는 바닥값 때문이 아니다 (사전 등록 밖)

`scripts/stage6_floor_diag.py` → `results/stage6/floor_diag.json`. 조정 구간 seed 20271106, lam5_map이다.

| 방법 | 지도에 들어간 보고 중 표적 보고 | 표적 보고 위치의 추정 / 참 밀도(중앙값) | 클러터 보고 위치의 추정 / 참 밀도 |
|---|---:|---:|---:|
| 5단계 고정 바닥값 | 31% | 30.0 | 1.13 |
| 6단계 바닥값 f 0.25 | 31% | 3.1 | 0.90 |

- 표적 보고 위치의 추정 밀도가 10배 줄었는데 결과는 같았다. 따라서 4·5단계 보고서의 추정("바닥값이 참 밀도보다 커서 생기는 손해")은 틀렸다.
- 다른 후보:
  - 지도에 들어가는 보고의 31%가 아직 확정되지 않은 표적의 보고다.
  - 첫 scan의 초기값(1/칸 부피)도 영향을 줄 수 있다.
  - 어느 쪽도 시험하지 않았다.
- 바닥값을 낮추면 표적 근처에서 존재 확률이 빨리 오를 것으로 생각했다. 그런데 확정 지연이 줄지 않았다. JIPDA 존재 갱신이 이 밀도 범위에서 이미 포화되어 있을 가능성이 있다. 이것도 확인하지 않았다.

### 7.4 예측 대 실제 (2부)

| 항목 | 에이전트 예측 | 실제 |
|---|---|---|
| 선택 | f = 0.5 | f = 0.25(세 후보 동점, 동점 규칙) |
| lam5_map 놓친 표적 손해(JIPDA 대비) | +0.29 → +0.10 (0.0–0.2) | **+0.29**(범위 밖, 변화 없음) |
| lam1000_map GOSPA | 3,959 m ±2% | **3,935 m**(범위 안) |
| 판정 | 개선 45%, 부분 45%, 없음 10% | **부분 개선**(규칙상, 실질 변화 없음) |

검수자 예측은 2부 항목이 없었다.

### 7.5 남은 문제 (2부)
- λ5 손해(놓친 표적 +0.29/scan, 확정 지연 +4.8 s)의 원인이 확인되지 않았다.
- 2부 후보 설계가 퇴화했다. 바닥값이 작동하려면 상한 창이 아닌 칸에 걸리는 규칙이 필요하다. 예: 칸 자신의 창 밀도에 대한 비율이 아니라 다른 기준.

## 11. commit

| commit | 내용 |
|---|---|
| 3c316d9 | 사전 등록(1부·2부), G1, Mode C 오차, 교차 사건, 데이터 바닥값, 단위 시험(실행 전) |
| 41b2cee | 퇴행 확인 결과, 큐·보고 스크립트 |
| 58a3ce1 | 1부 결과(13개 구간), 전체 퇴행 비교(commit 메시지의 "520 runs"는 잘못이고, 비교한 run은 1,040개다) |
| 322fd48 | 사후 분석(G1 거절, 항공기별 귀속) |
| 9cb6976 | 1부 보고서(21:08 push) |
| e228a04 | 2부 조정(후보 퇴화), f 0.25 동결 |
| (이 commit) | 2부 평가, 사후 확인, 이 보고서 최종본 |
