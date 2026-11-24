"""Render a 50 Hz G1 reference npz (converter output or make_combo_clip combo) to an mp4.

  MUJOCO_GL=egl python tools/video2motion/render_npz_preview.py <clip.npz> <out.mp4> \
      [--transition START END] [--follow] [--cam_yaw DEG]

Unlike render_preview.py there is no source video (a combo has none), so the robot is rendered alone with a fixed
camera by default: travel and heading changes read the same way they do in the reference. --transition shades the
frames make_combo_clip inserted, and the frame counter is burned in so a seam can be located exactly.
Headless: MUJOCO_GL=egl (NVIDIA) or MUJOCO_GL=osmesa.
"""

import argparse
import os

import imageio.v2 as imageio
import mujoco
import numpy as np

import g1_model

ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
ap.add_argument("npz")
ap.add_argument("out")
ap.add_argument("--robot_xml", default=None, help="default: $G1_XML, else bundled G1 XML")
ap.add_argument("--transition", type=int, nargs=2, default=None, metavar=("START", "END"))
ap.add_argument("--follow", action="store_true", help="camera follows the root xy (default: fixed wide shot)")
ap.add_argument("--cam_yaw", type=float, default=None, help="world heading (deg) the camera looks along +180")
ap.add_argument("--height", type=int, default=480, help="output height in px (4:3)")
ap.add_argument("--distance", type=float, default=2.6, help="camera distance [m]; solo panel, so closer than render_preview.py")
args = ap.parse_args()

z = np.load(args.npz)
root = z["body_pos_w"][:, 0]
quat = z["body_quat_w"][:, 0]  # wxyz
joint = z["joint_pos"]
fps = float(np.asarray(z["fps"]).reshape(-1)[0]) if "fps" in z else 50.0

m = g1_model.load_g1(args.robot_xml, floor=True)
H, W = args.height // 2 * 2, int(args.height * 4 / 3) // 2 * 2
m.vis.global_.offwidth, m.vis.global_.offheight = max(W, m.vis.global_.offwidth), max(H, m.vis.global_.offheight)
d = mujoco.MjData(m)
r = mujoco.Renderer(m, H, W)
cam = mujoco.MjvCamera()
yaw0 = args.cam_yaw if args.cam_yaw is not None else float(np.degrees(g1_model.yaw_xyzw(quat[0, [1, 2, 3, 0]])))
cam.distance, cam.elevation, cam.azimuth = args.distance, -10, yaw0 + 180
center = 0.5 * (root[:, :2].min(0) + root[:, :2].max(0))

try:
    import cv2
except ImportError:  # the counter is optional
    cv2 = None

w = imageio.get_writer(args.out, fps=fps, macro_block_size=1)
for t in range(len(joint)):
    d.qpos[:3] = root[t]
    d.qpos[3:7] = quat[t]
    d.qpos[7:] = joint[t]
    mujoco.mj_kinematics(m, d)
    cam.lookat[:] = [*(root[t, :2] if args.follow else center), 0.75]
    r.update_scene(d, cam)
    img = r.render()
    if cv2 is not None:
        in_trans = args.transition is not None and args.transition[0] <= t < args.transition[1]
        cv2.putText(img, f"{t:4d}  {t / fps:6.2f}s", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 0, 255) if in_trans else (255, 255, 255), 2, cv2.LINE_AA)
        if in_trans:
            cv2.putText(img, "TRANSITION", (12, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
    w.append_data(img)
w.close()
print(args.out, len(joint), f"frames @ {fps:g} fps")
