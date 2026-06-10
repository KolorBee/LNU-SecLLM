# Go2 + Hesai FAST-LIO2 现场使用说明

## 1. 基础环境

每个新终端先执行：

```bash
cd /home/star/unitree-go2-fan
source /opt/ros/humble/setup.bash
source install/setup.bash
```

也可以直接使用脚本，脚本会自动 source 环境：

```bash
cd /home/star/unitree-go2-fan
```

## 2. 打开建图

FAST-LIO2 + 3D 累计地图 + 2D 投影地图：

```bash
./scripts/fast_lio_2d_mapping.sh
```

默认行为是新开一张内存地图，相当于自动带上：

```bash
restart_map:=true
```

如果上一次建图进程没有退干净，脚本会拒绝继续启动，避免 RViz 继续显示上一轮
内存中的 `/lio_cloud_map` 或 `/map`。确认要清掉旧后台并重新开始时使用：

```bash
./scripts/fast_lio_2d_mapping.sh replace_existing:=true restart_map:=true
```

当前默认雷达外参已按现场安装修正：

```text
base_link -> hesai_lidar:
  x=0.00, y=0.00, z=0.10
  yaw=-0.22689280275926285 rad
  约等于顺时针 13 度
```

如果现场还需要微调，可以直接覆盖：

```bash
./scripts/fast_lio_2d_mapping.sh lidar_tf_yaw:=-0.20
```

常看数据：

```bash
ros2 topic hz /lidar_points
ros2 topic hz /imu_lio
ros2 topic hz /lio_odom
ros2 topic hz /map
ros2 run tf2_ros tf2_echo map base_link
```

保存 3D 地图：

```bash
ros2 service call /save_lio_cloud_map std_srvs/srv/Trigger '{}'
```

保存 2D 栅格地图：

```bash
ros2 service call /save_lio_2d_map std_srvs/srv/Trigger '{}'
```

默认保存目录：

```text
/home/star/go2_maps/fast_lio2/
```

## 3. 打开导航 dry-run

先只打开 Nav2 规划与代价地图，不让 Nav2 控制机器狗：

```bash
./scripts/fast_lio_nav2.sh
```

确认 RViz 中这些内容正常：

- `2D Occupancy Map Flat` 有地图。
- `Nav2 Global` 和 `Nav2 Local` 没有持续报错。
- `Go2 Body Marker` 或 `RobotModel` 与真实狗方向一致。
- `/lio_odom` 连续、无瞬移。

确认后再允许 Nav2 命令进入 Unitree 控制桥：

```bash
./scripts/fast_lio_nav2.sh start_go2_cmd_bridge:=true
```

未充分验证地图和定位前，不要打开 `start_go2_cmd_bridge:=true`。

RViz 顶部使用普通 `2D Goal Pose`。当前已增加 `go2_goal_pose_bridge`，会把 RViz
发布到 `/goal_pose` 的普通目标转换成 Nav2 的 `/navigate_to_pose` action。终端中应看到：

```text
[go2_goal_pose_bridge]: goal_pose #...
[go2_goal_pose_bridge]: NavigateToPose goal accepted
```

注意：`./scripts/check_fast_lio_nav2.sh` 末尾的 `Interpretation:` 是固定诊断说明，
不是报错本身。真正要看的是它上方列出的 action、`/cmd_vel`、`sport_ctrl`、
`/api/sport/request` 状态。

当前 RViz 配置已移除 `2D Pose Estimate`、`Nav2 Goal`、`Publish Point`：

- `2D Pose Estimate` 发布 `/initialpose`，但 FAST-LIO 方案不运行 AMCL，没有节点订阅。
- `Publish Point` 发布 `/clicked_point`，当前导航栈没有使用这个点。
- `Nav2 Goal` 插件在本现场配置中不如普通 `/goal_pose` 路线稳定，统一改用
  `2D Goal Pose -> go2_goal_pose_bridge -> /navigate_to_pose`。

打开控制桥后，终端中应能看到 `sport_ctrl` 的诊断：

```text
bridge stats: cmd_count=..., request_count=..., cmd_publishers=..., sport_subscribers=...
```

判断方法：

- 点 Nav2 Goal 后 `cmd_count` 增长：Nav2 已经输出 `/cmd_vel`。
- `request_count` 增长：桥接节点已把速度转成 `/api/sport/request`。
- `sport_subscribers` 应大于 0：机器狗运动 API 端能被 DDS 发现。
- 若 `cmd_count=0`，问题在 Nav2 规划/控制器没有输出速度。
- 若 `cmd_count>0` 但机器狗不动，检查机器狗是否站立、是否在可运动模式、遥控器/手机 App 是否抢占控制。

当前导航不是完整 3D 导航，而是“3D FAST-LIO 建图 + 2D 栅格投影 + Nav2 平面导航 +
局部 3D 点云障碍层”的 2.5D 方案。它可以保存三维点云，也可以把障碍投影成二维栅格
给 Nav2 使用；但它不会理解楼梯的高度、坡度、踏面，也不会做足端落点规划。因此不要
把当前版本用于自主上下楼梯。楼梯场景需要 elevation map / traversability map / legged
planner 一类更高层的地形可通行性模块。

新增的 2.5D 地形感知模块见：

```bash
./scripts/terrain_mapping.sh
```

当前地形模块采用偏严格调参，并默认融合：

```text
/lio_cloud_registered
/lio_cloud_map
/camera/depth/color/points
/camera/camera/depth/color/points
```

D435i 只有在本机 ROS2 中存在 PointCloud2 topic 时才会参与；SSH 视频预览不能直接作为
地形点云。若 Orin 上有 ROS2 RealSense 驱动，可用：

```bash
D435I_REMOTE_BACKEND=ros2 ./scripts/start_d435i_camera.sh view:=false
```

详细说明：

```text
/home/star/unitree-go2-fan/docs/terrain_mapping_usage_cn.md
```

## 4. 真实腿部关节状态

当前默认启动会发布静态站姿，保证 RViz 里一直能看到完整狗模型。

如果已经有机器狗官方 `/lowstate`，现在关闭静态关节后会自动把 `/lowstate`
转成 `/joint_states`，RViz 中四肢会跟随真实关节：

```bash
./scripts/fast_lio_nav2.sh publish_static_joint_states:=false
```

建图入口同理：

```bash
./scripts/fast_lio_2d_mapping.sh publish_static_joint_states:=false
```

如果你通过 CycloneDDS 或 go2_ros2_sdk 收到其他 LowState 话题，也可以显式指定：

```bash
source /opt/ros/humble/setup.bash
source /home/star/go2_ros2_sdk/install/setup.bash
source /home/star/unitree-go2-fan/install/setup.bash

ros2 launch go2_slam_nav fast_lio_nav2.launch.py \
  use_rviz:=true \
  start_lidar_driver:=true \
  start_go2_cmd_bridge:=false \
  publish_static_joint_states:=false \
  publish_lowstate_joint_states:=true \
  lowstate_topic:=/lowstate
```

检查：

```bash
ros2 topic hz /joint_states
ros2 topic echo /joint_states --once
```

## 5. 参考 go2_ros2_sdk 的无线连接

`/home/star/go2_ros2_sdk` 支持 WebRTC Wi-Fi。它能发布：

- `/joint_states`
- `/camera/image_raw`
- `/camera/camera_info`
- `/go2_states`
- `/odom`

第一次使用前需要构建：

```bash
cd /home/star/go2_ros2_sdk
source /opt/ros/humble/setup.bash
git submodule update --init --recursive

# 已验证的最小 WebRTC/视频依赖；比完整 requirements.txt 少装 torch/open3d 等大件。
/usr/bin/python3 -m pip install --user \
  aiortc==1.9.0 aiohttp paho-mqtt python-dotenv \
  wasmtime pycryptodome pydub requests

rosdep install --from-paths . --ignore-src -r -y
colcon build --symlink-install --packages-select go2_interfaces go2_robot_sdk
```

运行轻量 driver，不启动它自带的 RViz/SLAM/Nav2：

```bash
cd /home/star/unitree-go2-fan
./scripts/go2_webrtc_driver.sh
```

默认 `ROBOT_IP=192.168.123.161`、`CONN_TYPE=webrtc`、`GO2_ENABLE_VIDEO=true`、
`GO2_DECODE_LIDAR=false`。

更推荐使用一键查看脚本：

```bash
cd /home/star/unitree-go2-fan
./scripts/start_go2_webrtc_camera.sh
```

该脚本会启动 `go2_ros2_sdk`，等待 `/camera/image_raw` 的真实第一帧，然后打开 viewer。
它不使用 SSH，也不启动 D435i RealSense 驱动。

停止 WebRTC camera driver：

```bash
./scripts/start_go2_webrtc_camera.sh stop:=true
```

注意：这一路是 Go2 前视彩色相机，不是 D435i 深度相机，因此只应期待：

```text
/camera/image_raw
/camera/camera_info
```

现场测试状态：WebRTC 到 `192.168.123.161` 可以握手，日志出现
`Robot 0 validated and ready` 和 `Video frame received`，并能创建标准
`/camera/image_raw` 发布者。但当前仍未收到可解码的第一帧，底层 H.264 仍报
`non-existing PPS 0 referenced`。已在本地 SDK 中尝试增加 RTCP PLI 关键帧请求，
但本轮测试未解决该编码参数缺失问题。

注意：使用 WebRTC 时，手机 App 要断开与机器狗的视频/控制连接，否则可能抢占连接。

## 6. D435i 深度相机

Go2 EDU 扩展坞上的 D435i 接在机器狗背部 Docking Station / Orin 上时，电脑本机
不会出现 `/dev/video*`。已确认当前 Orin 地址为：

```text
192.168.123.18
user: unitree
password: 123
```

Go2 内部运动控制电脑 / MCU 是 `192.168.123.161`，能 ping，但不能 SSH。

当前 Orin 是 Ubuntu 20.04.5，已安装 librealsense、RealSense 工具和 ROS1 Noetic
版 `realsense2_camera`，但没有 ROS2 RealSense 节点。因此现阶段 PC 本地显示 D435i
采用“Orin 采集 + SSH 传回本机显示”，不依赖 ROS1/ROS2 图像桥。

已新增一键脚本：

```bash
cd /home/star/unitree-go2-fan
./scripts/start_d435i_camera.sh
```

默认行为：

- 本机检测到 RealSense USB 设备时，在本机启动 D435i。
- 本机没有检测到 D435i 时，通过 SSH 连接 `ORIN_HOST=192.168.123.18`，在 Orin 上用
  RealSense C++ SDK 采集，再把 JPEG 帧传回本机显示。
- 默认窗口：`d435i_color`、`d435i_depth`、`d435i_infra1`。
- 第一次启动会把一个小采集器传到 Orin 并编译；后续可加 `--no-build` 跳过编译。

如果 Orin 地址或用户名不同：

```bash
ORIN_HOST=<Orin IP> ORIN_USER=<用户名> ./scripts/start_d435i_camera.sh
```

直接使用 SSH 查看器并跳过远端编译：

```bash
./scripts/view_d435i_over_ssh.sh --no-build
```

降低带宽，只看彩色和深度：

```bash
./scripts/view_d435i_over_ssh.sh --streams color,depth --fps 15
```

非 GUI 测试取帧：

```bash
./scripts/view_d435i_over_ssh.sh --no-build --no-display --frames 6 --streams color,depth
```

停止远端残留采集进程：

```bash
./scripts/start_d435i_camera.sh stop:=true
```

默认配置是 `640x480@15Hz`，显示 color、depth、infra1。可用环境变量调整：

```bash
D435I_WIDTH=640 D435I_HEIGHT=480 D435I_FPS=15 D435I_STREAMS=color,depth \
  ./scripts/start_d435i_camera.sh
```

如果后续在 Orin 上安装 ROS2 RealSense 节点，可以切回旧的远端 ROS2 后端：

```bash
D435I_REMOTE_BACKEND=ros2 ./scripts/start_d435i_camera.sh
```

Unitree 私有 `/frontvideostream` 目前能收到包，但存在 DDS 反序列化异常和 H.264
PPS/SPS 不完整问题，画面会绿屏或只解出少量坏帧；不建议把它作为 D435i/双目深度相机的主入口。

同时打开 Go2 前视彩色相机和 D435i：

```bash
./scripts/view_go2_all_cameras.sh
```

注意：Go2 前视彩色相机仍走 `go2_ros2_sdk` WebRTC，当前能握手但还存在 H.264 关键帧/PPS
问题；D435i SSH 查看器已实测可解出彩色和深度帧。

D435i 可以作为近场障碍判断的辅助传感器，尤其适合狗头前方 `0.2-2.5 m` 的低矮障碍、
桌腿、人腿、箱子等近距离目标。建议后续接入方式：

- 在 Orin 或本机发布 D435i 的 ROS2 `PointCloud2` 或 depth image。
- 补充 `base_link -> d435i_*` 的 TF，狗头安装时还要考虑头部俯仰角变化。
- 把 D435i 点云经过距离、高度、自身遮挡过滤后接入 Nav2 `local_costmap` 的
  voxel/obstacle layer，作为局部避障，不作为全局定位或全局地图主传感器。
- 保留禾赛雷达作为主 SLAM/全局地图来源，因为 D435i 视场窄，强光、反光、低纹理和远距离
  深度可靠性都不如激光雷达。

## 7. Nav2 运动桥诊断

如果 `./scripts/fast_lio_nav2.sh start_go2_cmd_bridge:=true` 后点目标狗不动，先运行：

```bash
./scripts/check_fast_lio_nav2.sh
```

重点看：

- Nav2 lifecycle 节点是否 `active`。
- `/navigate_to_pose` 是否有 action server。
- 点目标后 `/cmd_vel_nav`、`/cmd_vel` 是否出现发布者和数据。
- `/sport_ctrl` 是否存在。
- `/api/sport/request` 是否有 Unitree 侧订阅者。

本轮已确认电脑能通过 CycloneDDS 看到 `/api/sport/request`、`/api/sport/response`、
`/sportmodestate`、`/lowstate`，运动控制电脑 DDS 通讯本身是通的。`sport_ctrl` 已将
`/api/sport/request` 发布 QoS 默认改为 `reliable`，可用下面参数切回：

```bash
./scripts/fast_lio_nav2.sh \
  start_go2_cmd_bridge:=true \
  go2_request_qos_reliability:=best_effort
```
