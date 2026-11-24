"""Render GVHMR's world-frame (global) view from an existing hmr4d_results.pt.

The original demo render OOM'd on a 4 GB GPU at 720x1280. HMR inference is already
done and saved, so this script only re-runs `render_global` at a reduced resolution.

    cd "$GVHMR_ROOT"
    "$GVHMR_PY" /path/to/video2motion_1_clip/scripts/render_gvhmr_global_lowres.py \
        --output-root /path/to/video2motion_1_clip/data/gvhmr \
        --video-name 1

"""

import argparse
from pathlib import Path

import torch
from einops import einsum
from hydra import compose, initialize_config_module
from hmr4d.configs import register_store_gvhmr
from hmr4d.utils.geo.hmr_cam import create_camera_sensor
from hmr4d.utils.geo_transform import apply_T_on_points, compute_T_ayfz2ay
from hmr4d.utils.smplx_utils import make_smplx
from hmr4d.utils.video_io_utils import get_video_lwh, get_writer
from hmr4d.utils.vis.renderer import (
    Renderer,
    get_global_cameras_static,
    get_ground_params_from_points,
)

# demo.py imports DemoPL, which registers the `model/gvhmr/gvhmr_pl_demo` config group.
import hmr4d.model.gvhmr.gvhmr_pl_demo  # noqa: F401
from tqdm import tqdm

CRF = 23


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-root", required=True)
    ap.add_argument("--video-name", required=True)
    ap.add_argument("--scale", type=float, default=0.5, help="render resolution multiplier")
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    with initialize_config_module(version_base="1.3", config_module="hmr4d.configs"):
        register_store_gvhmr()
        cfg = compose(
            config_name="demo",
            overrides=[
                f"video_name={args.video_name}",
                "static_cam=True",
                f"output_root={args.output_root}",
            ],
        )

    pred = torch.load(cfg.paths.hmr4d_results, map_location="cpu", weights_only=False)
    smplx = make_smplx("supermotion").cuda()
    smplx2smpl = torch.load("hmr4d/utils/body_model/smplx2smpl_sparse.pt").cuda()
    faces_smpl = make_smplx("smpl").faces
    J_regressor = torch.load("hmr4d/utils/body_model/smpl_neutral_J_regressor.pt").cuda()

    smplx_out = smplx(**{k: v.cuda() for k, v in pred["smpl_params_global"].items()})
    pred_ay_verts = torch.stack([torch.matmul(smplx2smpl, v_) for v_ in smplx_out.vertices])

    def move_to_start_point_face_z(verts):
        verts = verts.clone()
        offset = einsum(J_regressor, verts[0], "j v, v i -> j i")[0]
        offset[1] = verts[:, :, [1]].min()
        verts = verts - offset
        T_ay2ayfz = compute_T_ayfz2ay(
            einsum(J_regressor, verts[[0]], "j v, l v i -> l j i"), inverse=True
        )
        return apply_T_on_points(verts, T_ay2ayfz)

    verts_glob = move_to_start_point_face_z(pred_ay_verts)
    joints_glob = einsum(J_regressor, verts_glob, "j v, l v i -> l j i")
    global_R, global_T, global_lights = get_global_cameras_static(
        verts_glob.cpu(), beta=2.0, cam_height_degree=20, target_center_height=1.0
    )

    length, width, height = get_video_lwh(cfg.video_path)
    rw, rh = int(width * args.scale) // 2 * 2, int(height * args.scale) // 2 * 2
    _, _, K = create_camera_sensor(rw, rh, 24)
    print(f"render {length} frames at {rw}x{rh} -> {cfg.paths.global_video}", flush=True)

    renderer = Renderer(rw, rh, device="cuda", faces=faces_smpl, K=K)
    scale, cx, cz = get_ground_params_from_points(joints_glob[:, 0], verts_glob)
    renderer.set_ground(scale * 1.5, cx, cz)
    color = torch.ones(3).float().cuda() * 0.8

    writer = get_writer(cfg.paths.global_video, fps=args.fps, crf=CRF)
    for i in tqdm(range(length), desc="Rendering Global"):
        cameras = renderer.create_camera(global_R[i], global_T[i])
        img = renderer.render_with_ground(verts_glob[[i]], color[None], cameras, global_lights)
        writer.write_frame(img)
    writer.close()
    torch.cuda.empty_cache()
    print("done:", Path(cfg.paths.global_video).resolve(), flush=True)


if __name__ == "__main__":
    main()
