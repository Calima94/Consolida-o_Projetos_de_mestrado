#!/usr/bin/env python3
"""Movement-replay check: the Gazebo elbow must follow a recorded human elbow.

Listens to the recorded angle (``/reach_grasp/elbow_deg``, from
``movement_replay``) and to the simulated elbow (``/joint_states``) and
reports, on a common 20 Hz grid:

* the excursion of each (max - min, degrees);
* the lag (0 to 3 s) at which the simulated elbow best matches the recording,
  and the correlation and RMS error at that lag.

The arm controller is the thesis one (P, kp = 1 on the elbow: a first-order
lag of about 1 s), so the simulated elbow is expected to trail the human one
and to cut the fastest peaks. Exit code 0 when the elbow follows the shape of
the movement (correlation >= 0.8 at the best lag and at least half of the
recorded excursion).
"""

import argparse
import math
import sys
import time

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64

GRID_HZ = 20.0


def resample(samples: list[tuple[float, float]], grid: np.ndarray) -> np.ndarray:
    t, v = np.array(samples).T  # -> [2, n]
    return np.interp(grid, t, v)


def compare(rec, sim, max_lag_s: float = 3.0, settle_s: float = 0.0) -> dict:
    """Best lag, correlation and RMS error of `sim` against `rec` (both [(t, deg)]).

    The first `settle_s` seconds after both streams exist are skipped: the arm
    starts extended (0 deg) and first has to reach the recorded rest angle.
    """
    t0 = max(rec[0][0], sim[0][0]) + settle_s
    t1 = min(rec[-1][0], sim[-1][0])
    grid = np.arange(t0, t1, 1.0 / GRID_HZ)
    r, s = resample(rec, grid), resample(sim, grid)
    best = None
    for k in range(int(max_lag_s * GRID_HZ) + 1):
        a, b = r[: len(r) - k], s[k:]  # sim delayed by k steps
        if len(a) < GRID_HZ * 5 or a.std() == 0 or b.std() == 0:
            continue
        c = float(np.corrcoef(a, b)[0, 1])
        if best is None or c > best[1]:
            best = (k / GRID_HZ, c, float(np.sqrt(np.mean((a - b) ** 2))))
    return {
        "seconds": float(grid[-1] - grid[0]) if len(grid) else 0.0,
        "rec_excursion": float(r.max() - r.min()) if len(r) else math.nan,
        "sim_excursion": float(s.max() - s.min()) if len(s) else math.nan,
        "lag_s": best[0] if best else math.nan,
        "corr": best[1] if best else math.nan,
        "rmse_deg": best[2] if best else math.nan,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=40.0)
    ap.add_argument("--settle", type=float, default=5.0, help="seconds skipped at the start")
    args = ap.parse_args()
    rclpy.init()
    node = Node("movement_checker")
    rec, sim = [], []
    node.create_subscription(
        Float64, "/reach_grasp/elbow_deg", lambda m: rec.append((time.monotonic(), m.data)), 50
    )

    def on_js(msg):
        if "elbow_joint" in msg.name:
            pos = msg.position[msg.name.index("elbow_joint")]
            sim.append((time.monotonic(), math.degrees(pos)))

    node.create_subscription(JointState, "/joint_states", on_js, 50)
    end = time.monotonic() + args.duration
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.05)
    node.destroy_node()
    rclpy.shutdown()
    if len(rec) < 100 or len(sim) < 100:
        print(f"FAIL: recorded={len(rec)} simulated={len(sim)} messages")
        sys.exit(1)
    m = compare(rec, sim, settle_s=args.settle)
    print(
        f"{m['seconds']:.0f} s compared: excursion recorded {m['rec_excursion']:.1f} deg, "
        f"simulated {m['sim_excursion']:.1f} deg; best lag {m['lag_s']:.2f} s, "
        f"correlation {m['corr']:.3f}, RMS error {m['rmse_deg']:.1f} deg"
    )
    ok = m["corr"] >= 0.8 and m["sim_excursion"] >= 0.5 * m["rec_excursion"]
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
