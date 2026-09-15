# Dog × ROBOCON 场地 (MuJoCo)

独立的 sim2sim 示例：HIMLoco 训练的狗 (model_3400.onnx) 在 ROBOCON 场地上跑，
不依赖 mujoco-gui / runtime_control 框架。

## 文件

| 文件 | 说明 |
|---|---|
| `dog_robocon.xml` | 场景：狗 + ROBOCON 场地（视觉网格 + 碰撞体） |
| `play_robocon.py` | 主脚本（ONNX 策略 + PD 控制 + 键盘控制） |
| `model_3400.onnx` | 训练好的策略 |
| `dog.yaml` | PD/观测归一化参数 |
| `meshes/` | 狗的 STL + 场地彩色网格 `robocon_000~028.obj`（按材质拆分，MuJoCo 不支持 MTL/顶点色，每个 mesh 用 rgba 上色） |

## 运行

```bash
~/miniconda3/envs/gym/bin/python play_robocon.py
```

键盘控制（evdev 全局监听，需要权限时 `sudo chmod 666 /dev/input/event*`）：
- `W/S` 前后、`A/D` 左右、`Q/E` 转向（按住移动，松手即停）
- `T` 重置、`R/F` 蹲下/站起、`Z` 高度复位、`X` 紧急停止

出生点在红方半场安全平地 `(-4, +2)`。改 `play_robocon.py` 顶部的
`SPAWN_POS` / `SPAWN_QUAT` 可换位置。

## 场地说明

- 视觉：Blender 导出的 DAE → OBJ → 按材质拆分成 29 个单色 mesh（红/蓝半场沿 Y 轴分：
  y>0 红方、y<0 蓝方；中央石柱到 z=1.7m；L1/L2 高台等）
- 碰撞：红/蓝半场、L1/L2 实体、围栏和阵列小方块由与视觉尺寸对齐的
  基础几何体承载；斜坡、阶梯、柱体和 L1 小障碍直接使用同一份渲染网格碰撞。
  碰撞体透明渲染，viewer 里
  按 `3` 可切换显示）
- 出生点 `(-4, +2)` 在红方半场，并避开 `x=-3` 的 L1 高台侧壁
  （视觉上网格沿 Y 轴分半场：y>0 红方、y<0 蓝方），
  换边改 `SPAWN_POS`
- 南北两侧的斜坡和阶梯已有实际碰撞，可用于上下 L1
- 中央柱体和侧面柱体均已启用网格碰撞
