"""Numerical checks: python -m unittest discover -s scripts -p 'test_*.py'."""
import json
import tempfile
import unittest
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from csv_to_npz import cap_velocity, motion_arrays, resample, velocity_limits, ROOT
from g1_model import load_g1


class ConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = load_g1()

    def rows(self, n):
        rows = np.zeros((n, 36))
        rows[:, 2] = 0.8
        rows[:, 6] = 1
        return rows

    def test_sampling_and_quaternion_shortest_path(self):
        rows = self.rows(31)
        time = np.arange(31) / 30
        rows[:, 0] = time * 2
        rows[:, 3:7] = Rotation.from_euler('z', time * 0.6).as_quat()
        rows[1::2, 3:7] *= -1
        sampled = resample(rows, 30, 50)
        self.assertEqual(sampled.shape, (51, 36))
        arrays = motion_arrays(self.model, sampled, 50)
        np.testing.assert_allclose(arrays['body_lin_vel_w'][:, 0], np.tile([2, 0, 0], (51, 1)), atol=1e-12)
        np.testing.assert_allclose(arrays['body_ang_vel_w'][:, 0], np.tile([0, 0, 0.6], (51, 1)), atol=1e-12)
        np.testing.assert_allclose(np.linalg.norm(arrays['body_quat_w'], axis=-1), 1, atol=1e-12)
        self.assertEqual(str(arrays['body_names'][0]), 'pelvis')

    def test_cap_and_recomputed_kinematics(self):
        rows = self.rows(8)
        rows[1:, 7] = 2
        limits = np.ones(29)
        capped = cap_velocity(rows, 50, limits)
        arrays = motion_arrays(self.model, capped, 50)
        self.assertLessEqual(np.max(np.abs(arrays['joint_vel'])), 1 + 1e-12)
        np.testing.assert_allclose(np.diff(capped[:, 7]), 0.02)
        data = mujoco.MjData(self.model)
        data.qpos[:] = np.r_[capped[-1, :3], capped[-1, [6, 3, 4, 5]], capped[-1, 7:]]
        mujoco.mj_kinematics(self.model, data)
        np.testing.assert_allclose(arrays['body_pos_w'][-1], data.xpos[1:])
        original = motion_arrays(self.model, rows, 50)
        self.assertGreater(np.max(np.abs(original['body_pos_w'] - arrays['body_pos_w'])), 0.1)

    def test_single_frame_and_bad_input(self):
        arrays = motion_arrays(self.model, resample(self.rows(1), 30, 50), 50)
        for key in ('joint_vel', 'body_lin_vel_w', 'body_ang_vel_w'):
            np.testing.assert_array_equal(arrays[key], 0)
        for rows in (np.zeros((2, 36)), np.full((2, 36), np.nan), np.zeros((2, 35))):
            with self.assertRaises(ValueError):
                resample(rows, 30, 50)
        self.assertEqual(len(resample(self.rows(2), 30, 50)), 2)

    def test_velocity_config_reordered_by_name(self):
        config = ROOT / 'configs/deploy_config_robot_constants.json'
        expected = velocity_limits(config, 0.6)
        values = json.loads(config.read_text())
        values['joint_names'].reverse()
        values['velocity_limit'].reverse()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(values))
            np.testing.assert_array_equal(velocity_limits(path, 0.6), expected)


if __name__ == '__main__':
    unittest.main()
