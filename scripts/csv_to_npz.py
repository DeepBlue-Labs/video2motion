#!/usr/bin/env python3
"""Convert G1 CSV (xyz, xyzw, 29 joints) to resampled motion NPZ files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from g1_model import CSV_COLS, G1_JOINT_NAMES, hemisphere_continuous, load_g1

ROOT = Path(__file__).resolve().parents[1]


def positive(value: float) -> float:
    value = float(value)
    if not np.isfinite(value) or value <= 0:
        raise ValueError("rates and velocity scales must be finite and positive")
    return value


def resample(rows: np.ndarray, input_fps: float, output_fps: float) -> np.ndarray:
    """Sample uniform timestamps within [0, (N-1)/input_fps]; never extrapolate."""
    input_fps, output_fps = positive(input_fps), positive(output_fps)
    rows = np.array(rows, dtype=np.float64, copy=True)
    if rows.ndim != 2 or rows.shape[1] != CSV_COLS or not len(rows) or not np.isfinite(rows).all():
        raise ValueError(f"expected nonempty finite CSV with {CSV_COLS} columns, got {rows.shape}")
    norms = np.linalg.norm(rows[:, 3:7], axis=1)
    if np.any(norms < 1e-12):
        raise ValueError("CSV contains a zero root quaternion")
    rows[:, 3:7] = hemisphere_continuous(rows[:, 3:7] / norms[:, None])
    if len(rows) == 1:
        return rows
    source = np.arange(len(rows)) / input_fps
    count = int(np.floor(source[-1] * output_fps + 1e-9)) + 1
    target = np.minimum(np.arange(count) / output_fps, source[-1])
    result = np.empty((count, CSV_COLS))
    for col in (*range(3), *range(7, CSV_COLS)):
        result[:, col] = np.interp(target, source, rows[:, col])
    result[:, 3:7] = hemisphere_continuous(Slerp(source, Rotation.from_quat(rows[:, 3:7]))(target).as_quat())
    return result


def derivative(values: np.ndarray, fps: float) -> np.ndarray:
    """Central differences internally, one-sided differences at clip boundaries."""
    return np.gradient(values, 1 / fps, axis=0) if len(values) > 1 else np.zeros_like(values)


def motion_arrays(model: mujoco.MjModel, rows: np.ndarray, fps: float) -> dict[str, np.ndarray]:
    """All model bodies except world; body 0 is pelvis, quaternions are wxyz.

    Velocities describe body-frame origins in world coordinates (not inertial COMs).
    Angular differences use relative rotations in world coordinates.
    """
    fps = positive(fps)
    data = mujoco.MjData(model)
    pos = np.empty((len(rows), model.nbody - 1, 3))
    quat = np.empty((len(rows), model.nbody - 1, 4))
    for i, row in enumerate(rows):
        data.qpos[:3] = row[:3]
        data.qpos[3:7] = row[[6, 3, 4, 5]]
        data.qpos[7:] = row[7:]
        mujoco.mj_kinematics(model, data)
        pos[i], quat[i] = data.xpos[1:], data.xquat[1:]
    angular = np.zeros_like(pos)
    for body in range(model.nbody - 1):
        quat[:, body] = hemisphere_continuous(quat[:, body])
        if len(rows) > 1:
            rot = Rotation.from_quat(quat[:, body, [1, 2, 3, 0]])
            intervals = (rot[1:] * rot[:-1].inv()).as_rotvec() * fps
            angular[0, body], angular[-1, body] = intervals[0], intervals[-1]
            angular[1:-1, body] = (intervals[:-1] + intervals[1:]) / 2
    return {
        "fps": np.asarray(fps),
        "joint_pos": rows[:, 7:].copy(),
        "joint_vel": derivative(rows[:, 7:], fps),
        "body_pos_w": pos,
        "body_quat_w": quat,
        "body_lin_vel_w": derivative(pos, fps),
        "body_ang_vel_w": angular,
        "joint_names": np.asarray(G1_JOINT_NAMES),
        "body_names": np.asarray([model.body(i).name for i in range(1, model.nbody)]),
    }


def velocity_limits(config: Path, scale: float) -> np.ndarray:
    values = json.loads(config.read_text())
    names = values["joint_names"]
    limits = np.asarray(values["velocity_limit"], dtype=np.float64)
    if len(names) != len(set(names)) or set(names) != set(G1_JOINT_NAMES):
        raise ValueError("velocity config must contain each G1 joint exactly once")
    if limits.shape != (len(names),) or not np.isfinite(limits).all() or np.any(limits <= 0):
        raise ValueError("velocity_limit must contain 29 finite positive values")
    return limits[[names.index(name) for name in G1_JOINT_NAMES]] * positive(scale)


def cap_velocity(rows: np.ndarray, fps: float, limits: np.ndarray) -> np.ndarray:
    """Forward slew-rate limiter; retains timing and first pose, may lag targets."""
    result = rows.copy()
    step = limits / positive(fps)
    for i in range(1, len(rows)):
        previous = result[i - 1, 7:]
        result[i, 7:] = previous + np.clip(rows[i, 7:] - previous, -step, step)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("out", type=Path, help="unlimited output .npz; capped output gets _vc suffix")
    parser.add_argument("--input-fps", type=float, default=30)
    parser.add_argument("--output-fps", type=float, default=50)
    parser.add_argument("--robot_xml", default=None)
    parser.add_argument("--velocity-config", type=Path, default=ROOT / "configs/deploy_config_robot_constants.json")
    parser.add_argument("--velocity-scale", type=float, default=0.75 * 0.8)
    parser.add_argument("--skip-velocity-cap", action="store_true")
    args = parser.parse_args()
    try:
        if args.out.suffix.lower() != ".npz":
            raise ValueError("output must have .npz extension")
        rows = resample(np.loadtxt(args.csv, delimiter=",", ndmin=2), args.input_fps, args.output_fps)
        model = load_g1(args.robot_xml)
        limits = None if args.skip_velocity_cap else velocity_limits(args.velocity_config, args.velocity_scale)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(args.out, **motion_arrays(model, rows, args.output_fps))
        print(f"Saved {args.out}: {len(rows)} frames @ {args.output_fps:g} Hz")
        if limits is not None:
            capped = cap_velocity(rows, args.output_fps, limits)
            arrays = motion_arrays(model, capped, args.output_fps)
            if np.any(np.abs(arrays["joint_vel"]) > limits + 1e-9):
                raise ValueError("post-cap velocity validation failed")
            arrays["joint_velocity_limit"] = limits
            destination = args.out.with_name(args.out.stem + "_vc.npz")
            np.savez_compressed(destination, **arrays)
            print(f"Saved {destination}: max joint correction {np.max(np.abs(capped[:, 7:] - rows[:, 7:])):.6g} rad")
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
