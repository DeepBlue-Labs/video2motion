# 从原始视频重新生成 Unitree G1 动作

目标：将原始视频重新处理为 Unitree G1 29 自由度动作。顺序为 **环境准备 → 30 fps 转码 → 人体框检测 → GVHMR 人体重建 → GMR 重定向、关节限位与接地 → CSV 转 NPZ → 关节限速 → 预览与仿真接入**。

本仓库提供视频至 CSV、CSV→50 Hz NPZ、关节限速的脚本和 G1 模型。GVHMR 代码、权重及 SMPL-X 模型需自行准备。

仓库已附带源视频 `inputs/gouquan.mp4`，不附带生成后的 CSV 或 NPZ。以下以该视频为输入。使用 Bash、Python 3.10–3.13；命令从仓库根目录执行，默认使用同一终端。`/path/to/...` 需替换为实际路径；换视频时同步修改文件名和动作名。新结果写入 `work/`。仓库不保留历史重建结果或预览，所有中间结果和预览由本次运行重新生成。

## 仓库文件整体说明

```text
video2motion/
├── README.md                              # 文件说明、环境准备及完整处理步骤
├── inputs/
│   └── gouquan.mp4                        # 本次需要重新处理的源视频，已纳入 Git 跟踪
├── scripts/                               # 主流程及辅助工具
│   ├── run_pipeline.sh                    # 串联转码→人体框→GVHMR→CSV→预览（不含 NPZ 转换/限速）
│   ├── shot_bbx.py                        # 检测人体框、处理切镜并平滑，生成 preprocess/bbx.pt
│   ├── gvhmr_to_supermimic.py              # GVHMR 结果→GMR 重定向→关节限位/接地→CSV 和 pickle
│   ├── retarget.sh                        # 重定向快捷入口，读取 gouquan 的 GVHMR 结果并生成同名 CSV
│   ├── g1_model.py                        # 共用 G1 关节顺序、模型加载、脚底几何与 CSV 工具
│   ├── render_preview.py                  # CSV + 30 fps 源视频→源视频与机器人并排预览
│   ├── csv_to_npz.py                      # CSV→50 Hz NPZ，关节限速并重新计算 body 数据
│   ├── render_npz_preview.py              # NPZ→机器人动作预览
│   ├── validate_repository.py             # 校验迁移文件；--model 额外编译模型并检查关节顺序
│   ├── render_gvhmr_global_lowres.py       # 可选：在 GVHMR 环境渲染世界视角人体重建预览
│   ├── extend_full.py                     # 可选：结合切镜、CSV 和人体重建扩展多镜头动作
│   └── render_full_preview.py             # 可选：渲染多镜头扩展结果，标注帧号与镜头
├── assets/
│   └── mjlab_unitree_g1/                  # 训练侧 G1 模型，供限位、脚底计算和渲染使用
│       ├── __init__.py                    # 模型包标识
│       ├── g1_constants.py                # 原模型包的机器人常量
│       └── xmls/
│           ├── g1.xml                     # G1 29 自由度 MJCF 入口
│           └── assets/                    # XML 引用的 STL 网格，需与模型一起保留
├── configs/
│   ├── deploy_config_hg_ft_325k.json       # 原部署配置，供核对关节顺序和限速设置
│   └── deploy_config_robot_constants.json # 原机器人常量，包含关节名称及速度限制
├── vendor/
│   └── gmr/                              # GMR 源码快照，只附带本包已有的 G1 资产
│       ├── general_motion_retargeting/    # 重定向核心实现
│       │   ├── ik_configs/                # 人体到机器人的 IK 映射配置
│       │   └── utils/                     # 人体动作读取与转换工具及其嵌入依赖
│       ├── assets/
│       │   ├── unitree_g1/                # GMR 求解用 mocap XML、网格和许可
│       │   └── body_models/smplx/         # 自行创建；放 SMPLX_NEUTRAL.npz，不纳入 Git
│       ├── scripts/                      # 上游示例脚本；本流程使用顶层 scripts/
│       ├── third_party/                  # 上游嵌入的第三方实现
│       ├── pyproject.toml                # GMR 包定义及依赖声明
│       ├── uv.lock                       # GMR 锁定依赖，供 uv sync --frozen 使用
│       ├── GIT_COMMIT.txt                # GMR 源码快照对应的 commit
│       ├── INSTALLED_VERSIONS.txt         # 原环境安装包版本记录
│       ├── README.md                     # 上游参考说明，当前操作路径以根 README 为准
│       └── LICENSE                       # GMR 许可；嵌入组件还需遵循各自许可
├── requirements.txt                      # 基础依赖范围，供数据处理、模型检查和渲染使用
├── requirements-retarget.txt             # 安装基础依赖及本地 GMR，不采用 GMR 锁文件
├── Makefile                              # check/model-check；retarget 处理 gouquan；preview 默认动作名为 1
├── .env.example                          # 路径模板，复制为 .env 并填写后手动 source .env
├── .gitignore                            # 忽略环境、运行产物和模型；保留 gouquan.mp4 跟踪例外
├── .gitattributes                        # 文本换行及二进制文件处理规则
├── .repository-manifest.json             # 迁移文件路径和 SHA-256；非所有新增文件的清单
├── .venv/                                # 运行时生成：基础 Python 环境，不随仓库提供
└── work/                                 # 运行时生成：本次处理结果，不纳入 Git
    ├── video2motion/
    │   ├── video30/                      # 本次转码后的 30 fps 视频
    │   ├── gvhmr/                        # 本次人体重建、预处理缓存及日志
    │   ├── csv_drift/                    # drift 接地 CSV 和 GMR pickle
    │   ├── csv_constant/                 # 可选：constant 接地 CSV 和 GMR pickle
    │   └── preview/                      # 本次 CSV/NPZ 预览视频
    └── npz/                              # 本次转换生成的 50 Hz NPZ 和限速结果
```

`vendor/gmr/.venv/` 由 `uv sync --frozen` 生成，SMPL-X 模型需自行下载。目录树中标注“运行时生成”或“自行创建”的内容未随仓库提供。处理 `gouquan.mp4` 时，使用第 6–8 步的显式命令。

## 从原始视频重新处理

### 第 0 步：进入仓库，检查文件完整性

**要做什么：** 解压或克隆后进入包含本 README 的目录，确认数据没有缺失或损坏。系统需要 Python 3.10–3.13。

```bash
cd /path/to/video2motion
export V2M_REPO="$PWD"
python3 --version
python3 scripts/validate_repository.py
mkdir -p inputs work
```

**成功标志：** 打印文件校验 `PASS`。确认自己的源视频已复制到 `inputs/gouquan.mp4`。此步骤仅检查文件，不安装依赖或生成动作。后续命令默认使用同一终端；新开终端时，重新进入仓库并设置 `V2M_REPO`。

### 第 1 步：建立数据读取和预览环境

**要做什么：** 安装 NumPy、MuJoCo 等依赖，确认 G1 模型能够加载。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/validate_repository.py --model
```

**输入：** `requirements.txt` 与 `assets/mjlab_unitree_g1/xmls/g1.xml`。

**输出与成功标志：** 生成 `.venv/`；文件校验和模型编译均打印 `PASS`，模型为 `nq=36, nv=35`。完成后继续准备重定向环境。

### 第 2 步：准备 GMR 与 SMPL-X 模型

**要做什么：** 安装 GMR 重定向依赖，并准备它读取 GVHMR 结果所需的 SMPL-X neutral 模型。

**1. 安装固定版本的 GMR。**

参考流程将 GMR 固定在 commit `25f56db79ac411258b377b6d4ccba0c8ff3372ac`，因为重定向脚本会访问 `configuration`、`rot_offsets1`、`error1/error2` 等内部接口。本仓库已在 `vendor/gmr/` 附带该版本源码快照，无需再克隆 GMR 或切换当前仓库的 commit。

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 和 Git 后，从仓库根目录执行：

```bash
export GMR_ROOT="$V2M_REPO/vendor/gmr"
export GMR_PY="$GMR_ROOT/.venv/bin/python"
command -v uv git
(cd "$GMR_ROOT" && uv sync --frozen --no-dev --no-cache)
```

该命令通过网络下载第三方依赖，在 `vendor/gmr/.venv/` 创建独立环境。`--frozen` 表示使用已有锁文件中的版本、不更新锁文件；`--no-dev` 跳过开发依赖；`--no-cache` 避免复用持久包缓存。这里不复制或复用其它项目的虚拟环境。

`smplx` Python 包会作为 GMR 依赖安装，锁定 commit 为 `1265df7ba545e8b00f72e7c557c766e15c71632f`。它是人体模型的读取代码，**不包含下一项所需的 SMPL-X 模型文件**。环境还会安装 MuJoCo、NumPy、SciPy、PyTorch、imageio 和 OpenCV 等依赖。参考项目说明 GMR 重定向可使用 CPU 版 PyTorch；本命令沿用本仓库锁文件，并不会自动切换 CPU 版本。

安装需要足够的下载、解压和环境存储空间。可先执行 `df -h "$GMR_ROOT" "${TMPDIR:-/tmp}"` 检查；若报 `No space left on device`，释放空间后重跑安装命令。仅看到 `.venv/` 目录并不表示依赖已安装成功。

**2. 准备 SMPL-X neutral 模型。**

在 [SMPL-X 官网](https://smpl-x.is.tue.mpg.de/) 注册并接受许可，下载 NPZ 格式的 `SMPLX_NEUTRAL.npz`。模型不随本仓库分发，也不会由 `uv sync` 下载。将获准使用的文件复制到 GMR 默认查找位置：

```bash
export SMPLX_BODY_MODELS="$GMR_ROOT/assets/body_models"
mkdir -p "$SMPLX_BODY_MODELS/smplx"
cp /path/to/SMPLX_NEUTRAL.npz "$SMPLX_BODY_MODELS/smplx/SMPLX_NEUTRAL.npz"
```

如果已为 GVHMR 下载了同一个模型，可用符号链接共享文件，替代上面的 `cp`；将源路径改为自己的 GVHMR 模型路径，目标位置应尚无同名文件：

```bash
ln -s /path/to/GVHMR/inputs/checkpoints/body_models/smplx/SMPLX_NEUTRAL.npz \
  "$SMPLX_BODY_MODELS/smplx/SMPLX_NEUTRAL.npz"
```

也可保留模型在其它目录，只设置 `SMPLX_BODY_MODELS=/path/to/body_models`，或在第 6 步传 `--body_models /path/to/body_models`。指定的是包含 `smplx/` 子目录的根目录，而不是 NPZ 文件本身；最终必须存在 `<body_models>/smplx/SMPLX_NEUTRAL.npz`。

**3. 检查环境与模型路径。**

GMR 使用的 SMPL-X 人体模型与本仓库的 G1 机器人 MJCF 是两类不同资产。G1 模型用于后续关节限位、脚底计算和预览，路径配置如下：

```bash
export G1_XML="$V2M_REPO/assets/mjlab_unitree_g1/xmls/g1.xml"
test -x "$GMR_PY" && test -s "$SMPLX_BODY_MODELS/smplx/SMPLX_NEUTRAL.npz" \
  && test -s "$G1_XML" && echo "模型路径 OK"
env -u PYTHONPATH -u PYTHONHOME PYTHONNOUSERSITE=1 "$GMR_PY" -c \
  'import general_motion_retargeting as gmr, torch, mujoco, smplx; print("GMR:", gmr.__file__); print("GMR imports OK")'
```

**成功标志：** 打印 `模型路径 OK` 和 `GMR imports OK`，GMR 导入路径位于本仓库的 `vendor/gmr/`。这验证了依赖和文件路径，模型能否正确读取还需第 6 步实际重定向确认。后续保持 `GMR_PY` 指向本仓库 `vendor/gmr/.venv/bin/python`，继续第 3 步准备 GVHMR。

### 第 3 步：准备视频重建环境

**要做什么：** 从视频重跑人体姿态估计时，自行安装 [GVHMR](https://github.com/zju3dv/GVHMR) 的代码、依赖、检查点及其所需人体模型，并准备系统 `ffmpeg`/`ffprobe`。具体下载和安装命令以该上游仓库 README 为准；本包没有包含 GVHMR 环境锁或完整补丁，不能仅凭本仓库离线完成此步骤。

按上游说明安装完成后，配置实际路径：

```bash
export GVHMR_ROOT=/path/to/GVHMR
export GVHMR_PY=/path/to/gvhmr/environment/bin/python
export V2M_WORK="$V2M_REPO/work/video2motion"
export GPU=0
ffmpeg -version
ffprobe -version
test -f "$GVHMR_ROOT/tools/demo/demo.py"
(cd "$GVHMR_ROOT" && "$GVHMR_PY" -c 'import torch, hmr4d; print("CUDA available:", torch.cuda.is_available())')
mkdir -p "$V2M_WORK/video30" "$V2M_WORK/gvhmr" "$V2M_WORK/preview"
```

**成功标志：** 两个视频工具能打印版本、demo 文件存在，GVHMR 环境可导入 `hmr4d`；使用 GPU 推理时应确认 CUDA 可用。导入通过不代表模型权重齐全，权重是否可用还需第 5 步实际推理确认。

需要保存路径配置时，复制 `.env.example` 为 `.env` 并填写实际路径，之后执行 `source .env`。`.env` 不会自动加载。

### 第 4 步：将源视频统一为 30 fps

**要做什么：** 统一输入帧率，使 GVHMR、CSV 与预览的帧序对应。不要直接把 25/60 fps 视频当作 30 fps 输入。

```bash
ffmpeg -nostdin -y -i "$V2M_REPO/inputs/gouquan.mp4" \
  -vf fps=30 -an -c:v libx264 -crf 17 -pix_fmt yuv420p \
  "$V2M_WORK/video30/gouquan.mp4"
ffprobe -v error -select_streams v:0 -count_frames \
  -show_entries stream=r_frame_rate,nb_read_frames -of default=noprint_wrappers=1 \
  "$V2M_WORK/video30/gouquan.mp4"
```

**输入：** `inputs/gouquan.mp4`。

**输出与成功标志：** `work/video2motion/video30/gouquan.mp4` 可播放，帧率为 `30/1`；帧数随输入视频长度变化。后续步骤使用本次生成的视频。

### 第 5 步：生成人体框，再运行 GVHMR 人体重建

**要做什么：** 先检测、平滑人体框，再从视频估计世界坐标下的 SMPL-X 动作。下列示例使用静态相机模式 `-s`，与原片段的处理方式一致。

先准备人体框（本例启用；不需要自定义人体框时可让 GVHMR 使用其默认预处理）：

```bash
CUDA_VISIBLE_DEVICES="$GPU" "$GVHMR_PY" "$V2M_REPO/scripts/shot_bbx.py" \
  "$V2M_WORK/video30/gouquan.mp4" "$V2M_WORK/gvhmr/gouquan/preprocess" \
  --gvhmr_root "$GVHMR_ROOT"
test -s "$V2M_WORK/gvhmr/gouquan/preprocess/bbx.pt"
```

再运行人体重建。GVHMR 会相对其源码目录查找检查点，因此在其目录内执行：

```bash
(cd "$GVHMR_ROOT" && CUDA_VISIBLE_DEVICES="$GPU" "$GVHMR_PY" tools/demo/demo.py \
  --video "$V2M_WORK/video30/gouquan.mp4" --output_root "$V2M_WORK/gvhmr" -s \
  > "$V2M_WORK/gvhmr/gouquan.log" 2>&1)
test -s "$V2M_WORK/gvhmr/gouquan/hmr4d_results.pt"
```

**输出：** `work/video2motion/gvhmr/gouquan/hmr4d_results.pt`，以及 `preprocess/` 缓存和 `work/video2motion/gvhmr/gouquan.log`。

**成功标志：** 推理日志未显示重建失败，`hmr4d_results.pt` 存在且非空。若 demo 在可视化阶段失败，先读日志确认姿态结果是否已完整保存；文件非空本身不能证明结果有效，还需第 6 步能正常读取。

### 第 6 步：GMR 重定向，执行关节限位与脚底接地

**要做什么：** 将 SMPL-X 人体动作映射到 G1 的 29 个关节，再依据仓库内的 G1 MJCF 裁剪关节限位，并进行接地修正。默认推荐 `drift` 模式；这些处理已包含在 `gvhmr_to_supermimic.py` 中，不需要另外执行限位脚本。

使用第 5 步生成的结果执行重定向，可运行 `bash scripts/retarget.sh`（默认动作名为 `gouquan`），或执行下列等效命令：

```bash
"$GMR_PY" scripts/gvhmr_to_supermimic.py \
  --gvhmr_pred "$V2M_WORK/gvhmr/gouquan/hmr4d_results.pt" --name gouquan \
  --floor_mode drift --out_dir "$V2M_WORK/csv_drift" \
  --robot_xml "$G1_XML" --init_from_human --restart_tol 0.1
```

输出为 `work/video2motion/csv_drift/gouquan.csv` 和 `1_gmr.pkl`。若需常数接地变体，将 `--floor_mode drift` 改为 `--floor_mode constant`，并把输出目录改为 `"$V2M_WORK/csv_constant"`。

**成功标志：** 脚本完成并打印帧数、接地与限位统计，CSV 每行有 36 列，数值有限。帧数应与本次 30 fps 输入视频对应。可对生成的 CSV 检查：

```bash
.venv/bin/python - <<'PYCODE'
import numpy as np
import os
from pathlib import Path
q = np.loadtxt(Path(os.environ["V2M_WORK"]) / "csv_drift/gouquan.csv", delimiter=",")
assert q.ndim == 2 and q.shape[1] == 36
assert np.isfinite(q).all()
assert np.allclose(np.linalg.norm(q[:, 3:7], axis=1), 1, atol=1e-5)
print("CSV OK:", q.shape)
PYCODE
```

重跑数值受模型版本、依赖和求解器影响，不保证与现有 CSV 逐位相同。

### 第 7 步：转换为 50 Hz NPZ，并进行关节限速

**要做什么：** 将 CSV 的根位置、根四元数和关节角从 30 Hz 重采样到 50 Hz，计算 body 位姿与速度，再按部署配置限制关节速度，最后重新计算与修改后姿态对应的运动量。

使用第 1 步环境直接转换，无需另取 SuperMimic 工具：

```bash
.venv/bin/python scripts/csv_to_npz.py \
  "$V2M_WORK/csv_drift/gouquan.csv" "$V2M_REPO/work/npz/gouquan.npz" \
  --input-fps 30 --output-fps 50 \
  --velocity-config configs/deploy_config_robot_constants.json \
  --velocity-scale 0.6
```

**输出：** `work/npz/gouquan.npz` 和 `work/npz/gouquan_vc.npz`。默认速度上限为 `0.75 × 0.8 × velocity_limit`，即 `0.6 × velocity_limit`。也可指定 `configs/deploy_config_hg_ft_325k.json`；脚本按关节名称对齐速度限制。只需转换时传 `--skip-velocity-cap`；自定义模型使用 `--robot_xml`，默认使用 `$G1_XML` 或仓库模型。

重采样使用位置/关节角线性插值、根四元数 SLERP；CSV 四元数从 xyzw 转为 NPZ 的 wxyz。采样覆盖原始时间区间内的完整 50 Hz 时间点，不向末帧之后外推，帧数为 `floor((N−1) × 50/30) + 1`。单帧输入输出单帧，速度为零。

限速采用逐帧关节角变化限制，保留第一帧、根轨迹和采样时间，快速运动时关节可能滞后，末帧也可能无法到达原目标。限速不会重新接地，应在第 8 步检查足底和动作质量。修改关节角后，脚本重新计算全部 body 位姿及速度。

NPZ 包含 `fps`、`joint_pos`、`joint_vel`、`body_pos_w`、`body_quat_w`、`body_lin_vel_w`、`body_ang_vel_w`，以及无需 pickle 即可读取的 `joint_names` 和 `body_names`。关节数组为 `(T, 29)`；body 使用 MJCF 顺序、排除 world，第 0 个为 pelvis。body 位置是 body 坐标系原点而非惯性质心，线/角速度均在世界坐标系，单位为 m/s 和 rad/s。速度以相邻帧差分计算，内部帧取前后区间平均，边界取单侧差分。

**成功标志：** 打印两个输出路径、帧数和最大限速修正量；限速结果的 `joint_vel` 不超过归档的 `joint_velocity_limit`。输出文件数值有限且四元数归一化；第 9 步可读取数组。仓库不附带预生成 NPZ，必须先完成第 6 步。

### 第 8 步：渲染预览，检查动作质量

**要做什么：** 查看源视频与 G1 动作是否对应，检查漂移、脚底离地、关节扭转以及限速后动作变化。预览需要可用的 EGL，或设置 `MUJOCO_GL=osmesa` 并安装对应系统库。

预览本次生成的 CSV 与转码视频：

```bash
mkdir -p "$V2M_WORK/preview"
MUJOCO_GL=egl .venv/bin/python scripts/render_preview.py \
  "$V2M_WORK/csv_drift/gouquan.csv" "$V2M_WORK/video30/gouquan.mp4" \
  "$V2M_WORK/preview/csv.mp4"
```

完成第 7 步并生成 `work/npz/gouquan_vc.npz` 后，预览该新文件：

```bash
MUJOCO_GL=egl .venv/bin/python scripts/render_npz_preview.py \
  work/npz/gouquan_vc.npz "$V2M_WORK/preview/npz.mp4"
```

**成功标志：** 输出 MP4 可播放，机器人动作连续，方向与源动作符合预期。可视化正常不等于真机验证通过。

### 第 9 步：读取动作，交付给训练或仿真项目

**要做什么：** 选定限速后的 NPZ，确认目标训练项目要求的关节顺序、body 顺序、帧率和四元数格式，再按该项目接口配置动作路径。

在第 1 步安装的环境中执行下面的 Python 示例，可读取第 7 步生成的动作：

```bash
.venv/bin/python - <<'PYCODE'
import numpy as np
with np.load("work/npz/gouquan_vc.npz", allow_pickle=False) as motion:
    joint_pos = motion["joint_pos"]          # (帧数, 29)，rad
    root_pos = motion["body_pos_w"][:, 0]    # m
    root_quat = motion["body_quat_w"][:, 0]  # wxyz
    print("fps:", motion["fps"].item(), "joint_pos:", joint_pos.shape)
PYCODE
```

**成功标志：** 打印 `fps: 50.0`，`joint_pos` 形状为 `(实际帧数, 29)`；目标项目能够加载动作并在仿真中正确播放。本仓库不包含训练、sim2sim 或真机控制入口，对应命令需按目标项目配置。

### 可选：用流水线代替第 4–6 步的逐条执行

完成第 0–3 步后，可执行以下命令，一次完成转码、人体框、GVHMR、两种接地 CSV 和 CSV 预览。无需再重复手动执行第 4–6 步。

```bash
export GMR_PY="${GMR_PY:-$GMR_ROOT/.venv/bin/python}"
SHOTS=1 bash scripts/run_pipeline.sh inputs/gouquan.mp4
```

默认输出：

| 阶段 | 输出路径（相对 `V2M_WORK`） |
|---|---|
| 30 fps 视频 | `video30/gouquan.mp4` |
| 人体重建与日志 | `gvhmr/gouquan/hmr4d_results.pt`、`gvhmr/gouquan.log` |
| drift 接地 CSV / GMR 字典 | `csv_drift/gouquan.csv`、`csv_drift/gouquan_gmr.pkl` |
| constant 接地 CSV / GMR 字典 | `csv_constant/gouquan.csv`、`csv_constant/gouquan_gmr.pkl` |
| CSV 并排预览 | `preview/gouquan.mp4` |

需要先跳过渲染时设置 `PREVIEW=0`；选择推理设备时设置 `GPU=0` 等。该流水线不包含第 7 步的 NPZ 转换和限速。

## 使用与复现边界

CSV 为 30 Hz、36 列：根位置 xyz（m）、根四元数 **xyzw**、29 个关节角（rad）。NPZ 的 `body_quat_w` 为 **wxyz**；目标关节顺序见 `scripts/g1_model.py` 和 `configs/`。限速后需保持关节速度与 body 位姿、速度的一致性。

单目估计可能存在漂移、快速摆臂误差或脚底离地；接地和限速后仍需检查动作，并在目标仿真项目验证。本仓库不包含训练或真机控制程序。

本次仓库整理验证了文件完整性、G1 模型加载和脚本语法，未重新执行真实视频的 GVHMR、GMR、后处理或渲染。以上步骤中的预期结果不是本次完整重跑的实测结论。

GMR 使用其 `vendor/gmr/LICENSE`；Unitree 资产许可见 `vendor/gmr/assets/unitree_g1/LICENSE`。其它组件遵循各自上游条款；原包未为 mjlab 模型目录单独附许可证，原脚本文档声明 MIT 但未附独立授权全文。SMPL-X/GVHMR 相关模型与产物须遵守相应许可，原报告标注非商业科研用途；源视频版权归原作者。
