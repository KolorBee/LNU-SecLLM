# 2.5D Terrain Mapping 使用说明

## 目标

`terrain_mapping` 是 FAST-LIO + Nav2 之后的地形感知层。它只做显示和规划约束，不发送
`/cmd_vel`，也不会控制机器狗上下楼梯。

当前第一版输出：

```text
/elevation_map
/elevation_cloud_debug
/traversability_grid
/stair_edges_marker
/terrain_debug_markers
/terrain_obstacle_cloud
/nav2_terrain_costmap
```

## 输入

默认融合当前工程实际 FAST-LIO 当前帧点云、FAST-LIO 累积局部图，以及可选 D435i
深度点云：

```text
/lio_cloud_registered
/lio_cloud_map
/camera/depth/color/points
/camera/camera/depth/color/points
```

其中 `/camera/depth/color/points` 和 `/camera/camera/depth/color/points` 是为了兼容
RealSense ROS2 不同命名空间。只有在本机 ROS2 topic 中真的能看到这些 PointCloud2
时，D435i 才会参与融合；单纯 SSH 视频预览不会生成地形点云。

## 启动

先启动 FAST-LIO 建图或 FAST-LIO Nav2，让 `/lio_cloud_registered`、TF 和 `/lio_odom`
正常出现。然后另开终端：

```bash
cd /home/star/unitree-go2-fan
./scripts/terrain_mapping.sh
```

不打开 RViz：

```bash
./scripts/terrain_mapping.sh use_rviz:=false
```

直接使用 ROS launch：

```bash
ros2 launch terrain_mapping terrain_mapping.launch.py
```

## RViz 查看

调试 RViz 固定坐标系为 `map`，默认显示：

- `Elevation Map`：高度归一化后的 2D 高程图。
- `Traversability Grid`：可通行性评分，`0` 可通行，`100` 不可通行，`-1` 未知。
- `Elevation Cloud`：每个已知格子的高程点。
- `Terrain Obstacle Cloud`：不可通行区域转换出的障碍物点云。
- `Stair Edges Marker`：疑似楼梯/台阶边缘。
- `Terrain Debug Markers`：统计信息。

手动打开：

```bash
rviz2 -d /home/star/unitree-go2-fan/src/terrain_mapping/rviz/terrain_mapping_debug.rviz
```

## 参数

主要参数在：

```text
/home/star/unitree-go2-fan/src/terrain_mapping/config/terrain_mapping.yaml
```

常调参数：

```yaml
local_map_radius: 5.0
local_map_forward: 5.0
grid_resolution: 0.05
min_z: -0.40
max_z: 1.50
obstacle_height_min: 0.06
max_slope_deg: 12.0
max_step_height: 0.08
max_roughness: 0.04
voxel_leaf_size: 0.05
robot_width: 0.38
safety_margin: 0.22
```

当前参数是偏严格的近场安全调试版：更容易把坡、坎、粗糙面和低矮障碍判为不可通行。
如果显示过红，优先微调 `max_slope_deg`、`max_step_height`、`max_roughness`。

## D435i 融合

如果要让 D435i 点云参与地形判断，需要启动 RealSense ROS2 点云，而不是只打开 SSH
视频窗口。例如在 Orin 已具备 ROS2 `realsense2_camera` 时：

```bash
D435I_REMOTE_BACKEND=ros2 ./scripts/start_d435i_camera.sh view:=false
```

然后确认至少有一个点云 topic：

```bash
ros2 topic list | grep -E 'depth.*/points'
ros2 topic hz /camera/depth/color/points
```

`terrain_mapping.launch.py` 默认会发布一个近似的 `base_link -> camera_link` 静态 TF：

```text
x=0.30, y=0.00, z=0.22, roll=0, pitch=0, yaw=0
```

如果狗头上的 D435i 实际安装位置差异较大，启动时可覆盖：

```bash
./scripts/terrain_mapping.sh d435i_tf_x:=0.28 d435i_tf_z:=0.24 d435i_tf_pitch:=0.10
```

## Nav2 接入

当前不自动修改 Nav2 主配置。示例文件：

```text
/home/star/unitree-go2-fan/src/terrain_mapping/config/nav2_terrain_costmap_example.yaml
```

里面展示了如何把 `/terrain_obstacle_cloud` 作为 local costmap 的额外 obstacle source。
正式接入前请先完成静止、平地慢走、简单障碍物、楼梯口静态观察四步测试。

## 验证命令

```bash
cd /home/star/unitree-go2-fan
./scripts/build.sh --packages-select terrain_mapping
source install/setup.bash

ros2 launch terrain_mapping terrain_mapping.launch.py use_rviz:=false

ros2 topic list | grep -E "terrain|elevation|stair|traversability"
ros2 topic hz /terrain_obstacle_cloud
ros2 topic hz /traversability_grid
ros2 topic hz /stair_edges_marker
```

## 测试顺序

1. 静止测试：机器狗不动，检查 elevation map 是否稳定。
2. 平地慢走：只手动遥控，不让 Nav2 控制，检查栅格是否乱跳。
3. 简单障碍物：前方放箱子，看 `/terrain_obstacle_cloud` 是否出现障碍。
4. 楼梯/台阶静态观察：只靠近楼梯，不下楼，看 `/stair_edges_marker` 是否标边缘。

## 当前限制

- 第一版是保守规则法，不是成熟的地形可通行性学习模型。
- 楼梯检测只做标记，不做自主上下楼。
- D435i 目前默认关闭；接入前需要先稳定发布 ROS2 点云和相机 TF。
- `/nav2_terrain_costmap` 只是可选 costmap 输入，不会自动覆盖当前 Nav2 配置。
