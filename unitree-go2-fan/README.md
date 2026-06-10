# unitree-go2-fan

`unitree-go2-fan` is a ROS 2 Humble workspace for Unitree Go2 mapping and navigation with a Hesai JT128 LiDAR.

This workspace vendors the project-local packages needed for the current workflow:

- `go2_slam_nav`: RTAB-Map LiDAR mapping, RViz config, Nav2 integration, Go2 marker/model helpers.
- `go2_cmd_processor`: Go2 command bridge used by the navigation launch.
- `go2_description`: Go2 URDF and mesh assets.
- `HesaiLidar_ROS_2.0`: Hesai ROS 2 LiDAR driver source.
- `spark_fast_lio`: FAST-LIO2 front-end source used for LiDAR-inertial odometry.
- `terrain_mapping`: 2.5D elevation/traversability debug layer.

Generated `build/`, `install/`, `log/`, rosbag/map databases, and saved PCD/PLY maps are intentionally not included.

`unitree_ros2` / `unitree_api` are intentionally external. Install/source Unitree's ROS 2 SDK first, or provide `/home/star/unitree_ros2/setup_go2.sh` before building/running. The bundled scripts source it automatically when present.

## Build

```bash
cd /home/star/unitree-go2-fan
./scripts/build.sh
```

If this workspace is moved or cloned elsewhere, run:

```bash
./scripts/configure_hesai_paths.sh
```

before building so `hesai_jt128.yaml` points to the local bundled Hesai correction files.

## Mapping

```bash
cd /home/star/unitree-go2-fan
./scripts/mapping.sh
```

Equivalent launch:

```bash
ros2 launch go2_slam_nav mapping.launch.py \
  use_rviz:=true use_rtabmapviz:=false \
  restart_map:=true localize_only:=false \
  use_go2_urdf:=true
```

Useful checks:

```bash
ros2 topic hz /lidar_points_slam
ros2 topic hz /odom
ros2 topic hz /map
ros2 run tf2_ros tf2_echo map base_link
```

## Save Map

While mapping is still running and `/map` is being published:

```bash
./scripts/save_maps.sh /home/star/unitree-go2-fan/maps mine_test_01
```

This saves:

- `mine_test_01.yaml`
- `mine_test_01.pgm`
- `mine_test_01.db`

## Navigation / Localization

If using a saved RTAB-Map database:

```bash
cp /home/star/unitree-go2-fan/maps/mine_test_01.db ~/.ros/rtabmap.db
```

Then start navigation:

```bash
cd /home/star/unitree-go2-fan
./scripts/nav.sh
```

In RViz, use `2D Pose Estimate` first if localization needs an initial pose, then use `2D Goal Pose` to send a Nav2 goal.

## Important Runtime Defaults

- LiDAR input to RTAB-Map: `/lidar_points_slam`
- Unitree odom relay: `/utlidar/robot_odom -> /odom`
- TF: `odom -> base_link`, `base_link -> hesai_lidar`
- RTAB-Map voxel size: `rtabmap_voxel_size:=0.15`
- LiDAR throttle: `lidar_throttle_rate:=2.0`
- LiDAR point stride: `lidar_point_stride:=1`

For higher detail, try:

```bash
./scripts/mapping.sh lidar_throttle_rate:=3.0 rtabmap_voxel_size:=0.12
```

If the machine becomes sluggish, use:

```bash
./scripts/mapping.sh lidar_throttle_rate:=2.0 rtabmap_voxel_size:=0.18
```

## FAST-LIO2 3D + 2D Nav2 Route

FAST-LIO2 is now the preferred LiDAR-inertial front-end for Hesai JT128 testing.
It publishes 3D maps and a projected Nav2-style 2D occupancy map.

Current defaults use the Hesai internal IMU with monotonic timestamp guarding and
a stable 2D map canvas for Nav2. The stable canvas can grow as new space is
discovered, but avoids repeated costmap resizing while the robot is stationary.

2D/3D mapping:

```bash
cd /home/star/unitree-go2-fan
./scripts/fast_lio_2d_mapping.sh
```

Save the accumulated 3D map:

```bash
ros2 service call /save_lio_cloud_map std_srvs/srv/Trigger '{}'
```

Save the projected 2D map:

```bash
ros2 service call /save_lio_2d_map std_srvs/srv/Trigger '{}'
```

Experimental Nav2 dry run:

```bash
./scripts/fast_lio_nav2.sh
```

This starts Nav2 without sending velocity commands to the dog. To allow Nav2
commands to reach the Unitree sport API, pass:

```bash
./scripts/fast_lio_nav2.sh start_go2_cmd_bridge:=true
```

Details: `docs/fast_lio_nav2_route.md`.

Chinese field runbook for mapping, Nav2 dry-run, optional Go2 WebRTC joint
states, and camera viewing: `docs/field_usage_cn.md`.
