robocon_ground这个文件夹要放在~/.gazebo/models这个路径下面
robocon_track.world这个文件直接放在主目录下面
运行用gazebo ~/robocon_track.world这个指令

## 一键启动（推荐）

不用手动复制文件，脚本会自动设置模型路径：

```bash
cd ~/桌面/rc/gazebo_models
./run_gazebo.sh              # 带界面启动
./run_gazebo.sh --headless   # 只起 gzserver（无界面）
```

原理：把本仓库路径加进 `GAZEBO_MODEL_PATH`，Gazebo 就能直接找到
`model://robocon_ground`，无需复制到 `~/.gazebo/models`。
