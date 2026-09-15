#!/usr/bin/env bash
# ROBOCON 场地 GazeBo 一键启动脚本
# 用法: ./run_gazebo.sh          启动带界面的 Gazebo
#       ./run_gazebo.sh --headless  只起 gzserver (无界面, 用于 ros/仿真服务)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 模型路径: 优先用本仓库内的 robocon_ground, 不需要复制到 ~/.gazebo/models
export GAZEBO_MODEL_PATH="${SCRIPT_DIR}${GAZEBO_MODEL_PATH:+:${GAZEBO_MODEL_PATH}}"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"

WORLD="${SCRIPT_DIR}/robocon_track.world"

if [ ! -f "$WORLD" ]; then
    echo "[错误] 找不到 world 文件: $WORLD"
    exit 1
fi
if [ ! -d "${SCRIPT_DIR}/robocon_ground" ]; then
    echo "[错误] 找不到模型目录: ${SCRIPT_DIR}/robocon_ground"
    exit 1
fi

# 检查 Gazebo 是否安装
if ! command -v gazebo &>/dev/null && ! command -v gzserver &>/dev/null; then
    echo "[错误] 未检测到 Gazebo, 安装方法 (Classic):"
    echo "    sudo apt install gazebo libgazebo-dev"
    echo "  或按官方教程: http://gazebosim.org/tutorials?cat=install"
    exit 1
fi

echo "[INFO] world:  $WORLD"
echo "[INFO] 模型路径: \$GAZEBO_MODEL_PATH = $GAZEBO_MODEL_PATH"

if [ "$1" = "--headless" ]; then
    echo "[INFO] 无界面模式启动 gzserver ..."
    exec gzserver --verbose "$WORLD"
else
    echo "[INFO] 启动 Gazebo ..."
    exec gazebo --verbose "$WORLD"
fi
