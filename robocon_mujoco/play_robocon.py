"""
Dog 在 ROBOCON 场地上跑 — 精简独立版，只依赖 mujoco / onnxruntime / yaml / numpy
由 eg/play.py 精简而来，去掉了 runtime_control 框架（浏览器面板、地图切换、随机化等）。

用法:
    python3 play_robocon.py                # 原生 MuJoCo viewer + 键盘控制
    python3 play_robocon.py --duration 10  # 限时运行
    python3 play_robocon.py --no-policy    # 只有 PD 站立, 不跑策略

键盘: W/S 前后  A/D 左右  Q/E 转向  (按住移动, 松手即停)
      T 重置   R/F 蹲/站   Z 高度复位
      若无 evdev 权限: sudo chmod 666 /dev/input/event*
"""
import time
from pathlib import Path
import argparse

import mujoco
import mujoco.viewer
import numpy as np
import onnxruntime as ort
import yaml

DEMO_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = DEMO_DIR / "dog.yaml"
DEFAULT_ONNX = DEMO_DIR / "model_3400.onnx"
DEFAULT_XML = DEMO_DIR / "dog_robocon.xml"

# 出生点: 红方半场 (视觉上 y>0 为红方), 机身朝向 +X
SPAWN_POS = np.array([-4.0, 2.0, 0.45])
SPAWN_QUAT = np.array([1.0, 0.0, 0.0, 0.0])

# ============================================================
#  RL/RR 映射 — IsaacGym 内部重排关节顺序
# ============================================================
# MuJoCo qpos 顺序: FL(0-2), FR(3-5), RR(6-8), RL(9-11)
# IsaacGym dof 顺序: FL(0-2), FR(3-5), RL(6-8), RR(9-11)
MUJOCO_TO_ISAAC = [0, 1, 2, 3, 4, 5, 9, 10, 11, 6, 7, 8]
ISAAC_TO_MUJOCO = [0, 1, 2, 3, 4, 5, 9, 10, 11, 6, 7, 8]

# 默认关节角 — IsaacGym 顺序: FL, FR, RL, RR
DEFAULT_ANGLES_ISAAC = np.array([
    -0.1, -0.8, -1.5,    # FL
     0.1,  0.8,  1.5,    # FR
     0.1, -1.0, -1.5,    # RL
    -0.1,  1.0,  1.5,    # RR
], dtype=np.float64)
DEFAULT_ANGLES_MUJOCO = DEFAULT_ANGLES_ISAAC[ISAAC_TO_MUJOCO]

TAU_LIMIT_HIP_THIGH = 23.7
TAU_LIMIT_CALF = 35.55

NUM_ONE_STEP_OBS = 46
HISTORY_LEN = 6
NUM_ACTIONS = 12


def quat_rotate_inverse(q, v):
    q_w = q[3]
    q_vec = q[:3]
    a = v * (2.0 * q_w ** 2 - 1.0)
    b = np.cross(q_vec, v) * q_w * 2.0
    c = q_vec * np.dot(q_vec, v) * 2.0
    return a - b + c


class ObsHistoryBuffer:
    def __init__(self, history_len, single_obs_dim):
        self.single_obs_dim = single_obs_dim
        self.buffer = np.zeros(history_len * single_obs_dim, dtype=np.float32)

    def push(self, new_obs):
        self.buffer[self.single_obs_dim:] = self.buffer[:-self.single_obs_dim].copy()
        self.buffer[:self.single_obs_dim] = new_obs

    def get(self):
        return self.buffer.reshape(1, -1).copy()

    def reset(self):
        self.buffer[:] = 0.0


# ============================================================
#  键盘控制 (evdev 全局监听, 可选)
# ============================================================
try:
    import evdev
except ImportError:
    evdev = None
import threading

_pressed_keys = set()

_DIR_SCANCODES = {} if evdev is None else {
    evdev.ecodes.KEY_W: 'w', evdev.ecodes.KEY_S: 's',
    evdev.ecodes.KEY_A: 'a', evdev.ecodes.KEY_D: 'd',
    evdev.ecodes.KEY_Q: 'q', evdev.ecodes.KEY_E: 'e',
    evdev.ecodes.KEY_UP: 'w', evdev.ecodes.KEY_DOWN: 's',
    evdev.ecodes.KEY_LEFT: 'a', evdev.ecodes.KEY_RIGHT: 'd',
}


def _find_keyboards():
    keyboards = []
    if evdev is None:
        return keyboards
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities()
            if evdev.ecodes.EV_KEY in caps and evdev.ecodes.KEY_W in caps[evdev.ecodes.EV_KEY]:
                keyboards.append(dev)
        except Exception:
            pass
    return keyboards


def _evdev_keyboard_thread(dev):
    try:
        for event in dev.read_loop():
            if event.type == evdev.ecodes.EV_KEY:
                d = _DIR_SCANCODES.get(event.code)
                if d:
                    if event.value == 1:
                        _pressed_keys.add(d)
                    elif event.value == 0:
                        _pressed_keys.discard(d)
    except Exception as e:
        print(f"[KEYBOARD] evdev 读取异常: {e}")


_kb_devs = _find_keyboards()

# 权限不足时, 尝试打开常见键盘设备
if not _kb_devs and evdev is not None:
    import glob, os
    for _path in sorted(glob.glob('/dev/input/event*')):
        try:
            _dev = evdev.InputDevice(_path)
        except PermissionError:
            continue
        except Exception:
            continue
        try:
            caps = _dev.capabilities()
            if evdev.ecodes.KEY_W in caps.get(evdev.ecodes.EV_KEY, []):
                _kb_devs.append(_dev)
        except Exception:
            pass

for _dev in _kb_devs:
    threading.Thread(target=_evdev_keyboard_thread, args=(_dev,), daemon=True).start()

if _kb_devs:
    print(f"[KEYBOARD] evdev: 监听 {len(_kb_devs)} 个键盘设备")
    for _dev in _kb_devs:
        print(f"  - {_dev.path}: {_dev.name}")
elif evdev is None:
    print("[KEYBOARD] ⚠ 未安装 evdev, 键盘控制不可用 (pip install evdev)")
else:
    print("[KEYBOARD] ⚠ 没有可用键盘设备, 键盘控制不可用")
    print("  修复: sudo chmod 666 /dev/input/event*  然后重新运行")
    print("  或永久: sudo usermod -aG input $USER 后注销重登")


def get_commands():
    vx = ( 1.0 if 'w' in _pressed_keys else -1.0 if 's' in _pressed_keys else 0.0)
    vy = ( 1.0 if 'a' in _pressed_keys else -1.0 if 'd' in _pressed_keys else 0.0)
    wz = ( 1.0 if 'q' in _pressed_keys else -1.0 if 'e' in _pressed_keys else 0.0)
    return np.array([vx, vy, wz], dtype=np.float32)


# ============================================================
#  观测构建 (46维, 与训练一致)
# ============================================================
def build_single_obs(quat_xyzw, omega, joint_q_isaac, joint_dq_isaac,
                     last_action_isaac, cmd, cfg, height_cmd=0.25):
    obs = np.zeros(NUM_ONE_STEP_OBS, dtype=np.float32)
    obs[0:3] = cmd * cfg["cmd_scale"]
    obs[3:6] = omega.astype(np.float32) * cfg["ang_vel_scale"]
    proj_gravity = quat_rotate_inverse(quat_xyzw, np.array([0., 0., -1.]))
    obs[6:9] = proj_gravity.astype(np.float32)
    obs[9:21] = ((joint_q_isaac - DEFAULT_ANGLES_ISAAC) * cfg["dof_pos_scale"]).astype(np.float32)
    obs[21:33] = (joint_dq_isaac * cfg["dof_vel_scale"]).astype(np.float32)
    obs[33:45] = last_action_isaac
    obs[45] = np.float32((height_cmd - 0.25) / 0.1)
    return np.clip(obs, -cfg["clip_obs"], cfg["clip_obs"])


def reset_robot(model, data):
    mujoco.mj_resetData(model, data)
    data.qpos[:3] = SPAWN_POS
    data.qpos[3:7] = SPAWN_QUAT
    data.qpos[7:19] = DEFAULT_ANGLES_MUJOCO
    data.qvel[:] = 0
    mujoco.mj_forward(model, data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--onnx", type=Path, default=DEFAULT_ONNX)
    parser.add_argument("--xml", type=Path, default=DEFAULT_XML)
    parser.add_argument("--no-policy", action="store_true")
    parser.add_argument("--duration", type=float, default=None)
    args = parser.parse_args()

    with DEFAULT_CONFIG.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    cfg = {
        "cmd_scale": np.array(config["cmd_scale"][:3], dtype=np.float32),
        "ang_vel_scale": config["ang_vel_scale"],
        "dof_pos_scale": config["dof_pos_scale"],
        "dof_vel_scale": config["dof_vel_scale"],
        "clip_obs": config.get("clip_obs", 100.0),
    }
    simulation_duration = args.duration or config["simulation_duration"]
    simulation_dt = config["simulation_dt"]
    control_decimation = config["control_decimation"]
    kps = np.array(config["kps"], dtype=np.float64)
    kds = np.array(config["kds"], dtype=np.float64)
    action_scale = config["action_scale"]

    mj_model = mujoco.MjModel.from_xml_path(str(args.xml))
    mj_model.opt.timestep = simulation_dt
    mj_data = mujoco.MjData(mj_model)
    reset_robot(mj_model, mj_data)

    if not args.no_policy:
        policy = ort.InferenceSession(
            str(args.onnx), providers=['CPUExecutionProvider'])
        input_name = policy.get_inputs()[0].name
        output_name = policy.get_outputs()[0].name

    obs_history = ObsHistoryBuffer(HISTORY_LEN, NUM_ONE_STEP_OBS)
    target_q_mujoco = DEFAULT_ANGLES_MUJOCO.copy()
    action_isaac = np.zeros(NUM_ACTIONS, dtype=np.float64)
    last_action_isaac = np.zeros(NUM_ACTIONS, dtype=np.float32)
    height_cmd = 0.25
    reset_flag = False
    count = 0

    print(f"\n  W/S:前后 A/D:左右 Q/E:转 T:重置 R:蹲下 F:站起 Z:高度复位")
    print(f"  [按住移动，松手即停]  地图: ROBOCON 场地, 出生: {SPAWN_POS}\n")

    # MuJoCo viewer 功能键回调
    def key_callback(keycode):
        nonlocal height_cmd, reset_flag
        if keycode == 82:      # R
            height_cmd = max(0.20, height_cmd - 0.02)
        elif keycode == 70:    # F
            height_cmd = min(0.35, height_cmd + 0.02)
        elif keycode == 90:    # Z
            height_cmd = 0.25
        elif keycode == 84:    # T
            reset_flag = True
        elif keycode == 88:    # X
            _pressed_keys.clear()

    with mujoco.viewer.launch_passive(mj_model, mj_data, key_callback=key_callback) as viewer:
        # 初始视角: 对准出生点的狗, 侧后上方跟随视角
        viewer.cam.lookat[:] = [SPAWN_POS[0], SPAWN_POS[1], 0.3]
        viewer.cam.distance = 2.5
        viewer.cam.azimuth = 135.0   # 从狗的侧后方看 (朝 +X 前进方向)
        viewer.cam.elevation = -20.0
        viewer.sync()

        start = time.time()
        while viewer.is_running() and time.time() - start < simulation_duration:
            step_start = time.time()
            cmd = get_commands()

            if reset_flag:
                reset_robot(mj_model, mj_data)
                obs_history.reset()
                last_action_isaac[:] = 0; action_isaac[:] = 0; count = 0
                reset_flag = False

            joint_q_mujoco = mj_data.qpos[7:19].astype(np.float64)
            joint_dq_mujoco = mj_data.qvel[6:18].astype(np.float64)
            joint_q_isaac = joint_q_mujoco[MUJOCO_TO_ISAAC]
            joint_dq_isaac = joint_dq_mujoco[MUJOCO_TO_ISAAC]

            quat_wxyz = mj_data.qpos[3:7]
            quat_xyzw = np.array([quat_wxyz[1], quat_wxyz[2], quat_wxyz[3], quat_wxyz[0]])
            omega = mj_data.qvel[3:6].astype(np.float64)

            if count % control_decimation == 0:
                if not args.no_policy:
                    single_obs = build_single_obs(
                        quat_xyzw, omega, joint_q_isaac, joint_dq_isaac,
                        last_action_isaac, cmd, cfg, height_cmd=height_cmd)
                    obs_history.push(single_obs)
                    action_raw = policy.run(
                        [output_name], {input_name: obs_history.get()})[0][0]
                    action_isaac[:] = np.clip(action_raw, -10.0, 10.0)
                    last_action_isaac = action_isaac.astype(np.float32)

                    target_q_isaac = action_isaac * action_scale + DEFAULT_ANGLES_ISAAC
                    target_q_mujoco = target_q_isaac[ISAAC_TO_MUJOCO]
                else:
                    target_q_mujoco = DEFAULT_ANGLES_MUJOCO.copy()

            # PD 控制 (MuJoCo 顺序, 力矩直接写入 ctrl, 由 ctrlrange 限幅)
            tau = kps * (target_q_mujoco - joint_q_mujoco) - kds * joint_dq_mujoco
            mj_data.ctrl[:NUM_ACTIONS] = tau

            mujoco.mj_step(mj_model, mj_data)
            count += 1

            if count % (control_decimation * 50) == 0:
                grav = quat_rotate_inverse(quat_xyzw, np.array([0., 0., -1.]))
                print(f"[{time.time()-start:.1f}s] Step {count} "
                      f"pos=({mj_data.qpos[0]:.2f},{mj_data.qpos[1]:.2f},{mj_data.qpos[2]:.2f}) "
                      f"vx={mj_data.qvel[0]:.2f} vy={mj_data.qvel[1]:.2f} grav_z={grav[2]:.3f}")

            viewer.sync()
            elapsed = time.time() - step_start
            if simulation_dt - elapsed > 0:
                time.sleep(simulation_dt - elapsed)

    print("\n[INFO] 仿真结束")


if __name__ == "__main__":
    main()
