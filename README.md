```
# ROBOCON 2027 女娲补天 - 场地仿真环境
这是第二十六届全国大学生机器人大赛 ROBOCON「女娲补天」竞技赛的场地仿真环境，包含 Gazebo Classic 和 MuJoCo 两套仿真平台，供 SLAM 建图、Nav2 导航验证、足式机器人（Dog）策略验证使用。

📖 项目背景
比赛场地为 11m × 11m 正方形，具有以下结构：
- 地面层：红蓝半场、启动区、储存区、地面公共区、五色石基座
- L1 层：高出地面 600mm，尺寸 6m × 6m，通过坡道或阶梯进入
- L2 层：高出地面 900mm，尺寸 3m × 3m，通过阶梯从 L1 进入
- 中央基座：位于 L2 层中央，用于放置五色石

本仓库提供了 两套仿真平台，各有用途：

| 平台 | 用途 | 特点 |
| ---- | ---- | ---- |
| Gazebo Classic | SLAM 建图、Nav2 导航验证 | 支持 ROS2 工具链，方便与 slam_toolbox、Nav2 集成 |
| MuJoCo | 足式机器人（Dog）运动策略验证 | 物理仿真精度高，适合强化学习策略测试 |

📁 目录结构
```

.
├── README.md
├── run_gazebo.sh          # Gazebo 一键启动脚本
├── robocon_track.world    # Gazebo 世界文件
├── robocon_ground/        # Gazebo 场地模型
│   ├── model.config
│   ├── model.sdf
│   └── meshes/
│       └── Untitled.dae   # Blender 导出的场地模型
├── play_robocon.py        # MuJoCo Dog 运行脚本
├── dog_robocon.xml        # MuJoCo 场景（场地 + Dog）
├── dog.yaml               # Dog 策略参数
├── model_3400.onnx        # Dog 强化学习策略
├── update_scene_visual.py # MuJoCo 场景视觉更新工具
└── meshes/                # MuJoCo 所需的所有网格
├── base.STL
├── FL_hip.STL
├── ...
└── robocon_*.obj      # 拆分的场地彩色网格

```

🚀 快速开始
## 一、环境依赖
通用依赖：
```bash
sudo apt update
sudo apt install gazebo libgazebo-dev
```

ROS2 Humble（用于 SLAM 和导航）：

```
sudo apt install ros-humble-gazebo-ros-pkgs
sudo apt install ros-humble-slam-toolbox
sudo apt install ros-humble-nav2-bringup
sudo apt install ros-humble-turtlebot3*
```

MuJoCo 相关：

```
pip install mujoco onnxruntime pyyaml numpy evdev
```

## 二、Gazebo 仿真

### 方式 A：一键启动（推荐）

```
cd ~/桌面/rc/gazebo_models
./run_gazebo.sh               # 带界面启动
./run_gazebo.sh --headless    # 只起 gzserver（无界面）
```

脚本会自动把当前目录加入 GAZEBO_MODEL_PATH，无需手动复制模型到 `~/.gazebo/models`。

### 方式 B：手动启动

把 robocon_ground 文件夹复制到 `~/.gazebo/models/`：

```
cp -r robocon_ground ~/.gazebo/models/
```

把 robocon_track.world 放到任意位置（例如主目录）。
启动 Gazebo：

```
gazebo ~/robocon_track.world
```

## 三、SLAM 建图与 Nav2 导航（ROS2 Humble）

启动 Gazebo 场地后，按以下步骤操作：

终端 1：启动 Gazebo 并加载场地

```
./run_gazebo.sh
```

终端 2：启动 TurtleBot3 仿真（或自己的机器人）

```
export TURTLEBOT3_MODEL=burger
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py
```

终端 3：启动 SLAM Toolbox

```
ros2 launch slam_toolbox online_async_launch.py
```

终端 4：启动 Rviz2 观察建图

```
rviz2
```

在 Rviz2 中 Add → Map 话题，即可看到地图实时生成。

终端 5：遥控机器人走完全场

```
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

按 `i` 前进、`j` 左转、`l` 右转、`,` 后退，走遍场地每个角落后保存地图：

```
ros2 run nav2_map_server map_saver_cli -f ~/robocon_map
```

得到 `~/robocon_map.pgm` 和 `~/robocon_map.yaml`，即可用于后续 Nav2 导航。

## 四、MuJoCo 仿真（Dog 机器人）

用于足式机器人运动策略的快速验证。
运行脚本

```
python3 play_robocon.py                # 原生 MuJoCo viewer + 键盘控制
python3 play_robocon.py --duration 10  # 限时运行 10 秒
python3 play_robocon.py --no-policy    # 只有 PD 站立，不跑策略
```

表格

| 键盘控制按键 | 功能 |
| --- | --- |
| W / S | 前后移动 |
| A / D | 左右移动 |
| Q / E | 转向 |
| T | 重置 |
| R / F | 蹲下 / 站起 |
| Z | 高度复位 |

注意：如果键盘控制不可用，可能是 `/dev/input/event*` 权限问题，执行：

```
sudo chmod 666 /dev/input/event*
```

或者永久解决：

```
sudo usermod -aG input $USER
```

然后注销重新登录。

🛠️ 工具脚本说明

### run_gazebo.sh

Gazebo 一键启动脚本，自动设置 GAZEBO_MODEL_PATH，支持带界面和无界面两种模式。

### update_scene_visual.py

用拆分后的彩色 mesh 替换 dog_robocon.xml 里的单一视觉网格。MuJoCo 不支持 MTL / 顶点色，所以场地模型需要按材质拆分成多个 .obj 文件。
使用方式：

```
python3 update_scene_visual.py path/to/dog_robocon.xml
```

📐 场地规格（来自比赛规则）

表格

| 元素 | 尺寸 | 颜色 RGB |
| --- | --- | --- |
| 比赛场地 | 11000mm × 11000mm | — |
| 围栏 | 高 80mm，厚 50mm | 100-62-0 |
| 中央隔板 | 长 11000mm，厚 50mm，高 80mm | 100-62-0 |
| 地面区（红） | 11m × 5.5m | 240-210-210 |
| 地面区（蓝） | 11m × 5.5m | 170-210-230 |
| 地面公共区 | 1200mm × 1200mm | 245-240-200 |
| 启动区 | 700mm × 700mm | 红：223-34-34 / 蓝：50-0-255 |
| 储存区 | 1000mm × 2000mm | 同地面色 |
| 五色石基座 | 高 500mm，直径 270mm | 100-62-0 |
| L1 层 | 6000mm × 6000mm，高 600mm | 红：235-180-160 / 蓝：150-215-220 |
| L2 层 | 3000mm × 3000mm，高 900mm | 190-190-185 |
| 中央基座 | 高 800mm，直径 270mm | 100-62-0 |

🧭 开发路线建议
按照分阶段开发策略，推荐以下顺序：

表格

| 阶段 | 目标 | 仿真平台 |
| --- | --- | --- |
| 第一阶段 | SLAM 建图、Nav2 导航验证 | Gazebo |
| 第二阶段 | TR 爬坡、上 L1 层 | Gazebo |
| 第三阶段 | TR 上 L2 层、精准停靠 | Gazebo |
| 第四阶段 | BR 机械臂抓取、建塔、五色石放置 | Isaac Sim |

> 
> 当前进度：第一阶段（地面层 SLAM 建图验证）

⚠️ 注意事项

- 模型路径：使用 run_gazebo.sh 时无需手动复制模型，脚本会自动设置路径。手动启动时需要把 robocon_ground 放到 `~/.gazebo/models/` 下。
- 碰撞体与视觉分离：model.sdf 中的碰撞体（collision）用基本几何体（box/cylinder），视觉（visual）引用 DAE/FBX 模型。这是为了保证物理仿真的稳定性和性能。
- MuJoCo 与 Gazebo 坐标差异：MuJoCo 中 y>0 为红方半场，Gazebo 中 x<0 为红方半场，注意坐标转换。
- 网络代理问题：如果 Gazebo 启动时报 libcurl: Failed to connect to 127.0.0.1 port 7897，请检查系统代理设置，或在终端执行：

```
unset http_proxy
unset https_proxy
```

📚 参考资料

- 比赛规则原文（第二十六届全国大学生机器人大赛 ROBOCON 女娲补天竞技赛规则 V0）
- Gazebo Classic 官方文档
- MuJoCo 官方文档
- ROS2 Humble 官方文档
- Nav2 官方文档
- slam_toolbox 官方文档

本项目仅供 ROBOCON 参赛队伍学习交流使用。

📝 更新日志

- 2026-09：完成地面层场地建模，导出 DAE 并导入 Gazebo，实现 SLAM 建图验证。
- 待更新：L1 层、L2 层、坡道、楼梯的建模与碰撞体配置。
