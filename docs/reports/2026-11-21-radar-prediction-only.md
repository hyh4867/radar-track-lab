# Radar Track Lab: 재시동 뒤 상태 확인과 "예측만" 분해 정리 (2026-11-21)

브랜치 `hyh4867/Radar`, 작업 위치 `projects/radar-track-lab/`. 공개 저장소, 사이트, 데모, README는 바꾸지 않았습니다.

## 결론

- **중단된 실험은 없었습니다.** `radar-oos4` screen은 재시동(2026-11-21 14:04 KST) 약 14시간 전인 2026-11-20 23:55에 끝났고, 결과는 그때 커밋·push되었습니다. 쓰다 만 파일이 없어서 지운 파일도, 다시 돌린 단위도 없습니다.
- 지시에 적힌 "같은 20 seed로 baseline + 예측만(등속 외삽)" 실험은 `radar-oos4`가 아니라 그 앞의 `predict_baseline` 실험입니다(2026-11-20 21:49 커밋). 이것도 끝나 있었습니다. `radar-oos4`는 같은 비교에 "출력 예측을 뺀 EKF"를 더한 네 방법을 표본 밖 14개 시나리오에 돌린 실험입니다.
- 스캔 끝 RMSE 차이 −353 m의 분해 (스히폴 평가 구간, seed 20개, 공통 표본, 짝 차이와 95% 구간):
  - **예측만으로 설명되는 부분**: 기준선에 등속 외삽만 붙이면(할당은 그대로) **−211.46 m [−213.30, −209.61]**, 전체 −353.26 m의 **59.9%**.
  - **필터·gating·할당이 더한 부분**: 그 위에서 EKF로 바꾸면 **−141.80 m [−143.35, −140.25]**, **40.1%**.
  - 단, 이 나눔은 순서에 따라 달라집니다. 출력 예측 없이 필터·gating·할당만 바꾸면 **−10.13 m [−10.47, −9.79]**(2.9%)뿐입니다. 나머지 −132.45 m [−133.78, −131.13](37.5%)는 둘이 함께 있어야 생기는 몫(상호작용)입니다. 필터가 추정한 속도로 외삽할 때 생기는 몫이며, 그 안에서 속도 추정과 할당의 몫은 나누지 못합니다. 그래서 "예측만 59.9%, 나머지 40.1%"는 기준선 → 예측 추가 → EKF 순서로 바꿨을 때의 값으로만 적어야 합니다.
  - 표본 밖 유효 12개 시나리오에서도 같은 모양입니다: 예측만 54.2–71.8%, 필터·gating·할당만 0.9–3.8%, 상호작용 26.6–42.2%.
- 새로 만든 것은 기존 run 파일을 읽어 위 분해를 계산하는 스크립트 하나(`scripts/audit_prediction_split.py`)와 그 출력, 이 보고서입니다. 시뮬레이션은 돌리지 않았습니다.

## 중단과 재개 기록

### 확인한 사실

| 시각 (KST) | 사건 | 근거 |
|---|---|---|
| 11-20 21:45 / 21:49 | predict_baseline 프로토콜 커밋 / 결과 커밋 (seed 20261106–20261125, 스히폴 평가 구간) | 커밋 `69e3b90` → `dcf0fc1`, `653c542` → `192cbc2` (rebase 전 → 후) |
| 11-20 23:07 / 23:13 | hold_ekf 프로토콜 / 결과 커밋 | `9ccdcc2` → `c6e2899`, `b770a55` → `a43782b` |
| 11-20 23:25 | four_methods_oos 프로토콜 커밋, 직후 `screen -dmS radar-oos4`로 실행 시작 | `fa54289` → `fa830f5`; 앞 보고서의 실행 명령 |
| 11-20 23:27–23:54 | 시나리오 14개 결과 파일이 하나씩 쓰임 | `results/audit/four_methods_oos/runs/*.json` 수정 시각 23:27:37–23:54:35 |
| 11-20 23:43 | 드론 세션이 메모리 여유 7%, 스왑 거의 가득 참을 기록 (드론 추론과 radar-oos4가 동시에 돎) | 드론 세션 기록 |
| 11-20 23:55:07 | `summary.json`, `summary.md` 작성 (실행 끝) | 파일 수정 시각 |
| 11-20 23:56 | 결과 커밋·push | `aca2901` → `9b4070a` |
| 11-21 12:17 | 앞 Radar 세션에 "끝났나요?" 질문, 응답은 로그인 오류로 실패 | 앞 세션 기록 |
| 11-21 14:04 | 맥 재시동 | `sysctl kern.boottime` |

### 결과 파일 점검 (2026-11-21 17:10 무렵)

- `results/audit/four_methods_oos/runs/` 14개 파일, `predict_baseline/runs.json`, `hold_ekf/runs.json` 모두 JSON으로 읽힙니다. 각 파일의 `runs`는 20개이고, seed는 20261106–20261125이며 중복이 없습니다.
- `git status`와 `git diff HEAD -- results/`는 비어 있었습니다. 커밋된 내용과 디스크의 내용이 같습니다.
- 마지막 커밋(11-20 23:57) 뒤에 바뀐 파일은 작업 트리에 없었습니다(`.venv`, `.git` 제외).
- 남아 있는 screen 세션이나 radar 쪽 잠금은 없었습니다.
- `summary.json`의 짝 차이와 구간을 seed별 값에서 따로 다시 계산했고, 소수 둘째 자리까지 같았습니다(아래 `audit_prediction_split.py` 출력의 첫 표).

그래서 다시 돌린 단위는 없습니다. 무거운 작업 잠금(`tools/heavy-run.sh`)은 test 실행에만 썼습니다.

## 결과

출처: `results/audit/prediction_split/summary.md`, `summary.json` (`scripts/audit_prediction_split.py`가 아래 세 run 파일에서 만듦).

- `results/audit/predict_baseline/runs.json`: 기준선(nn), 기준선 + 출력 예측(nnp), EKF. 세 방법 공통 표본.
- `results/audit/hold_ekf/runs.json`: 위 셋 + 출력 예측을 뺀 EKF(ekfh). 네 방법 공통 표본.
- `results/audit/four_methods_oos/runs/*.json`: 네 방법, 표본 밖 14개 시나리오.

수치는 scan-end RMSE(m), seed 20개, 기준 조건(Pd 0.9, λ 5, σ_θ 0.15°)입니다. [ ]는 seed 짝 차이의 95% t-구간입니다. 구간은 고정된 한 교통 구간에서의 시뮬레이션 변동만 나타냅니다.

### 1. 사전 등록한 순서: 기준선 → 출력 예측 추가 → EKF (세 방법 공통 표본)

| 단계 | 짝 차이 (m) | 전체 대비 |
|---|---:|---:|
| 기준선 → 기준선 + 출력 예측 (예측만) | −211.46 [−213.30, −209.61] | 59.9% |
| 기준선 + 출력 예측 → EKF (필터·gating·할당) | −141.80 [−143.35, −140.25] | 40.1% |
| 기준선 → EKF | −353.26 [−354.91, −351.61] | 100% |

seed별 비의 평균은 59.9% [59.4, 60.3]이고, seed별 범위는 57.5–61.2%입니다.

감사의 −353.41 m(두 방법 각자의 표본)나 −353.93 m(두 방법 공통 표본)와 조금 다른 것은 공통 표본이 세 방법 교집합(16,768개/run)이어서입니다.

### 2. 두 순서와 상호작용 (네 방법 공통 표본)

네 방법은 2×2 배치입니다. 추적기(기준선 / EKF+GNN) × 출력(마지막 갱신에 고정 / scan 끝까지 외삽).

| 항 | 짝 차이 (m) | 전체 대비 |
|---|---:|---:|
| 전체: 기준선 → EKF | −353.42 [−355.00, −351.83] | 100% |
| A1: 기준선에 출력 예측만 추가 | −210.83 [−212.71, −208.96] | 59.7% |
| A2: 그 위에 필터·gating·할당 | −142.59 [−144.08, −141.10] | 40.3% |
| B1: 필터·gating·할당만 (출력 예측 없음) | −10.13 [−10.47, −9.79] | 2.9% |
| B2: 그 위에 EKF 출력 예측 | −343.29 [−344.92, −341.65] | 97.1% |
| 상호작용: B2 − A1 (= A2 − B1) | −132.45 [−133.78, −131.13] | 37.5% |

전체 = A1 + B1 + 상호작용 = −210.83 − 10.13 − 132.45 m.

읽는 법:
- **예측만의 몫(주효과)**: 약 211 m. 필터 없이 두 점 속도로 외삽만 해도 이만큼 줄어듭니다.
- **필터·gating·할당만의 몫(주효과)**: 약 10 m. 출력을 마지막 갱신 위치에 두면 EKF의 더 정확한 갱신 위치(update-time RMSE 172.8 → 125.8 m)와 더 적은 끊김이 scan-end RMSE에는 거의 보이지 않습니다.
- **함께 있어야 생기는 몫**: 약 132 m. 필터가 추정한 속도로 외삽하면 두 점 속도로 외삽할 때보다 더 줄어드는 부분입니다. "필터·gating·할당이 더한 부분"을 묻는다면, 혼자서는 10 m, 예측과 함께라면 142 m입니다.
- 두 행의 "출력 예측"은 내용이 다릅니다(기준선은 두 점 속도, EKF는 필터 속도). 그래서 상호작용 항은 "필터 속도가 외삽을 더 좋게 만드는 몫"과 "할당 차이"를 따로 나누지 못합니다. 이 상호작용 항은 사전 등록하지 않은 기술 통계입니다. 두 순서의 몫(59.7%, 97.1%)은 hold_ekf 프로토콜에 사전 등록된 값입니다.

### 3. 표본 밖 14개 시나리오 (네 방법 공통 표본, seed 20개 평균)

| 시나리오 | 표적/scan | 전체 (m) | A1 예측만 | B1 필터·gating·할당만 | 상호작용 | A1 몫 | B1 몫 | 상호작용 몫 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| EGLL 11-06 | 92.6 | −353.0 | −232.6 | −5.7 | −114.7 | 65.9% | 1.6% | 32.5% |
| EGLL 11-11 | 65.7 | −372.4 | −254.5 | −5.1 | −112.8 | 68.3% | 1.4% | 30.3% |
| EHAM 11-06 14:40 | 49.9 | −351.3 | −209.3 | −9.5 | −132.6 | 59.6% | 2.7% | 37.7% |
| EHAM 11-11 | 35.2 | −411.5 | −287.8 | −8.7 | −114.9 | 70.0% | 2.1% | 27.9% |
| ENGM 11-06 | 14.4 | −367.2 | −260.1 | −3.3 | −103.8 | 70.8% | 0.9% | 28.3% |
| ENGM 11-11 | 10.1 | −445.3 | −319.6 | −7.5 | −118.3 | 71.8% | 1.7% | 26.6% |
| KATL 11-06 | 118.0 | −322.6 | −177.9 | −12.2 | −132.6 | 55.1% | 3.8% | 41.1% |
| KATL 11-11 | 104.6 | −306.9 | −166.3 | −10.9 | −129.6 | 54.2% | 3.6% | 42.2% |
| LSZH 11-06 | 40.8 | −404.0 | −283.2 | −7.4 | −113.4 | 70.1% | 1.8% | 28.1% |
| LSZH 11-11 | 22.4 | −474.4 | −317.7 | −11.2 | −145.5 | 67.0% | 2.4% | 30.7% |
| YSSY 11-06 | 44.9 | −232.1 | −155.4 | −2.2 | −74.6 | 66.9% | 0.9% | 32.1% |
| YSSY 11-11 | 26.0 | −265.9 | −176.7 | −3.7 | −85.5 | 66.5% | 1.4% | 32.1% |
| EHAM 11-06 04:30 (유효하지 않음) | 4.8 | −523.1 | −378.6 | −10.4 | −134.0 | 72.4% | 2.0% | 25.6% |
| EHAM 11-06 02:00 (유효하지 않음) | 1.0 | −590.8 | −438.7 | −8.5 | −143.6 | 74.3% | 1.4% | 24.3% |

유효 12개(scan당 표적 5대 이상) 범위: A1 54.2–71.8%, B1 0.9–3.8%, 상호작용 26.6–42.2%. 시나리오별 상호작용의 95% 구간은 모두 0에서 멉니다(가장 좁은 쪽 YSSY 11-06 [−76.1, −73.1]). 같은 공항의 두 날과 같은 날의 여러 공항은 독립 표본이 아니므로 시나리오 사이의 퍼짐은 범위로만 적습니다. 교통량이 많은 KATL에서 상호작용 몫이 가장 큽니다(41–42%).

### 이 결과로 말할 수 있는 것과 없는 것

- 말할 수 있는 것: "−353 m 중 약 211 m(60%)는 필터 없이 등속 외삽만 붙여도 사라진다. 필터·gating·할당만 바꾸고 외삽하지 않으면 약 10 m(3%)만 사라진다. 나머지 약 132 m(37%)는 필터가 추정한 속도로 외삽할 때 생긴다."
- 말할 수 없는 것: "예측 60%, 필터·할당 40%"를 순서 없이 적는 것. 앞 보고서들과 같은 규칙입니다(59.9%만 따로 인용하지 않음).
- 상호작용 안에서 속도 추정과 할당의 몫을 나누려면 기준선에 필터 속도를 쓰는 변형 같은 새 실험이 필요합니다. 이번에는 하지 않았습니다.

## 재현 명령

```bash
cd projects/radar-track-lab
.venv/bin/python scripts/audit_prediction_split.py   # 1초 미만, run 파일만 읽음
```

## rebase와 push

최신 `origin/main`(`3fbea3b`) 위로 rebase했습니다. main의 새 커밋 3개(`ecd49cf` 작업 규칙 파일, `c814fa5` 공용 무거운 작업 잠금, `3fbea3b` 정리 보고서)는 `projects/radar-track-lab/` 밖의 파일만 바꿔서 충돌이 없었습니다. 브랜치는 이미 push되어 있었으므로 `--force-with-lease`로 push했습니다. 커밋 내용과 작성 시각은 그대로이고 해시만 바뀌었습니다. 앞 보고서들에 적힌 해시는 아래 표로 찾을 수 있습니다. 이전 head는 로컬 태그 `radar-pre-rebase-20261121`(`aca2901`)로 남겨 두었습니다(push하지 않음).

| rebase 전 | rebase 후 | 커밋 |
|---|---|---|
| `3b54665` | `25ed64d` | EKF+GNN tracker |
| `c914729` | `cd7c1b4` | PPI web demo |
| `a17d3b8` | `65e3940` | README lead metrics, dense clutter |
| `c4ed4d7` | `84af237` | public release report |
| `12d2a1b` | `4ab215f` | stage 2 preregistration |
| `af45ee2` | `cb9a76d` | stage 2 IMM, parameter freeze |
| `51df627` | `434f772` | stage 2 evaluation runs |
| `50b2c6f` | `5c8d0c2` | stage 2 results |
| `d8e416b` | `9e41612` | stage 2 report |
| `3be6698` | `509285e` | audit protocol |
| `94f4767` | `8ca496d` | evaluation audit |
| `69e3b90` | `dcf0fc1` | predict_baseline protocol |
| `653c542` | `192cbc2` | predict_baseline results |
| `9ccdcc2` | `c6e2899` | hold_ekf protocol |
| `b770a55` | `a43782b` | hold_ekf results |
| `fa54289` | `fa830f5` | four_methods_oos protocol |
| `aca2901` | `9b4070a` | four_methods_oos results |

## test

rebase 뒤 작업 트리에서 `tools/heavy-run.sh`로 잠금을 잡고 screen(`radar-tests`) 안에서 실행했습니다. 잠금은 astra 평가 작업이 잡고 있어서 그 뒤에 기다렸습니다.

```
heavy-run: waiting for PID 90004
heavy-run: acquired lock (PID 92745)
start 2026-11-21 17:15:27 +0900
============================= test session starts ==============================
platform darwin -- Python 3.12.8, pytest-9.2.0, pluggy-1.7.0 -- ~/orca/workspaces/astronomy-ai-portfolio/Radar/projects/radar-track-lab/.venv/bin/python
cachedir: .pytest_cache
rootdir: ~/orca/workspaces/astronomy-ai-portfolio/Radar/projects/radar-track-lab
configfile: pyproject.toml
collecting ... collected 45 items

tests/test_audit.py::test_update_common_sample_with_asynchronous_times_and_exclusions PASSED [  2%]
tests/test_audit.py::test_scan_end_common_sample_drops_the_hard_pair_and_can_flip_the_comparison PASSED [  4%]
tests/test_audit.py::test_duplicate_and_mismatched_keys_are_errors PASSED [  6%]
tests/test_audit.py::test_paired_difference_and_percent_reduction_by_hand PASSED [  8%]
tests/test_audit.py::test_unpaired_target_is_excluded_from_the_scan_end_sample PASSED [ 11%]
tests/test_audit.py::test_recording_does_not_change_scores_and_reproduces_both_rmses[ekf] PASSED [ 13%]
tests/test_audit.py::test_recording_does_not_change_scores_and_reproduces_both_rmses[nn] PASSED [ 15%]
tests/test_audit.py::test_recording_does_not_change_scores_and_reproduces_both_rmses[imm] PASSED [ 17%]
tests/test_audit.py::test_prediction_only_baseline_extrapolates_the_last_two_detections_by_hand PASSED [ 20%]
tests/test_audit.py::test_prediction_only_baseline_shares_the_baseline_association_and_leaves_its_scores_alone PASSED [ 22%]
tests/test_audit.py::test_three_way_common_scan_end_sample PASSED        [ 24%]
tests/test_audit.py::test_ekf_hold_output_reports_the_last_updated_position_and_shares_the_ekf_updates PASSED [ 26%]
tests/test_audit.py::test_ekf_hold_output_position_by_hand PASSED        [ 28%]
tests/test_ekf_tracker.py::test_single_target_straight_line_converges PASSED [ 31%]
tests/test_ekf_tracker.py::test_ekf_reduces_error_vs_raw_measurement PASSED [ 33%]
tests/test_ekf_tracker.py::test_gate_threshold_and_mahalanobis PASSED    [ 35%]
tests/test_ekf_tracker.py::test_gating_rejects_far_detection PASSED      [ 37%]
tests/test_ekf_tracker.py::test_hungarian_assignment_global_optimum PASSED [ 40%]
tests/test_ekf_tracker.py::test_m_of_n_confirmation_and_deletion PASSED  [ 42%]
tests/test_ekf_tracker.py::test_track_ids_persist_and_are_not_reused PASSED [ 44%]
tests/test_ekf_tracker.py::test_componentwise_assignment_matches_dense_solve PASSED [ 46%]
tests/test_geo.py::test_azimuth_convention_clockwise_from_north PASSED   [ 48%]
tests/test_geo.py::test_polar_cartesian_round_trip PASSED                [ 51%]
tests/test_geo.py::test_wrap_pi PASSED                                   [ 53%]
tests/test_geo.py::test_polar_cov_cross_range PASSED                     [ 55%]
tests/test_geo.py::test_geodetic_enu_round_trip_and_scale PASSED         [ 57%]
tests/test_geo.py::test_velocity_rotation_meridian_convergence PASSED    [ 60%]
tests/test_imm.py::test_transition_matrix_is_a_markov_semigroup PASSED   [ 62%]
tests/test_imm.py::test_ct_predict_exact_circle_small_omega_and_jacobian PASSED [ 64%]
tests/test_imm.py::test_turn_is_detected_and_tracked_better_than_cv PASSED [ 66%]
tests/test_imm.py::test_straight_line_accuracy_not_worse_than_cv PASSED  [ 68%]
tests/test_imm.py::test_nees_on_model_matched_truth PASSED               [ 71%]
tests/test_imm.py::test_imm_single_target_management_like_ekf PASSED     [ 73%]
tests/test_metrics_repro.py::test_gospa_known_values PASSED              [ 75%]
tests/test_metrics_repro.py::test_same_seed_reproducible_and_different_seed_differs PASSED [ 77%]
tests/test_metrics_repro.py::test_clutter_rate_matches_lambda PASSED     [ 80%]
tests/test_metrics_repro.py::test_hermite_exact_for_constant_acceleration PASSED [ 82%]
tests/test_metrics_repro.py::test_anees_bounds_contain_dof PASSED        [ 84%]
tests/test_privacy.py::test_dbflags_exclusion PASSED                     [ 86%]
tests/test_stage2.py::test_extractor_writes_no_identifier_column PASSED  [ 88%]
tests/test_stage2.py::test_processed_point_files_hold_only_allowed_columns PASSED [ 91%]
tests/test_stage2.py::test_committed_outputs_carry_no_identifier_fields PASSED [ 93%]
tests/test_stage2.py::test_sites_are_outside_korea_and_extract_script_applies_dbflags PASSED [ 95%]
tests/test_stage2.py::test_truth_turn_rate_matches_the_known_manoeuvre PASSED [ 97%]
tests/test_stage2.py::test_lost_track_in_a_known_turn_is_classified_as_turn PASSED [100%]

============================== 45 passed in 4.82s ==============================
exit=0
end 2026-11-21 17:15:32 +0900
```

## 바꾸지 않은 것

- 공개 저장소 `hyh4867/radar-track-lab`, 포트폴리오 사이트, `radar-track-lab.vercel.app` 데모.
- README, `docs/INTERVIEW.md`, 기존 결과 파일. 새 파일은 `scripts/audit_prediction_split.py`, `results/audit/prediction_split/summary.{json,md}`, 이 보고서뿐입니다.
- main 병합은 하지 않았습니다.
