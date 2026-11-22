"""Stone Soup (b) lambda 200 diagnostic: does our LBP iteration cap explain the split? (post hoc)

Runs scripts/stage3_stonesoup_b.one(200, 20261106, n_scans, analytic Jacobian) with our marginals_lbp
wrapped: "capped" = frozen settings (tol 1e-10, max 2000 iterations), "uncapped" = tol 1e-13, 1e6 iterations.
    .venv/bin/python scripts/stage3_stonesoup_b_lbpdiag.py capped|uncapped N_SCANS
"""
import sys, json
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
import radar_track_lab.jpda as J
import stage3_stonesoup_b as B
orig = J.marginals_lbp
mode = sys.argv[1]; n = int(sys.argv[2])
hits = {"calls": 0, "maxed": 0, "max_it": 0}
def wrap(w0, W, tol=1e-10, max_iter=2000):
    if mode == "uncapped":
        tol, max_iter = 1e-13, 1_000_000
    b0, Bm, it = orig(w0, W, tol, max_iter)
    hits["calls"] += 1; hits["max_it"] = max(hits["max_it"], it); hits["maxed"] += int(it >= max_iter)
    return b0, Bm, it
J.marginals_lbp = wrap
r = B.one(200, 20261106, n, True)
print(json.dumps({"mode": mode, "n_scans": n, "lbp": hits, "first_split": r["first_scan_sets_differ"],
                  "share_within_1cm": r["share_within_1cm"], "max_pos_diff_m": r["max_pos_diff_m"]}))
