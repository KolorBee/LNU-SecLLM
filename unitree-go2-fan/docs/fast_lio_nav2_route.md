# FAST-LIO2 + 2D/2.5D Nav2 Route

This route uses FAST-LIO2 as the LiDAR-inertial odometry and 3D mapping front-end.
Nav2 consumes a projected 2D OccupancyGrid and a filtered local 3D obstacle cloud.

## Current Pipeline

```text
Hesai JT128 /lidar_points + /lidar_imu
  -> spark_fast_lio
  -> /lio_odom, /lio_cloud_registered, /lio_cloud_base
  -> go2_cloud_accumulator
  -> /lio_cloud_map
  -> go2_lio_grid_mapper
  -> /map
  -> Nav2 global costmap static layer

/lio_cloud_base
  -> go2_cloud_throttle
  -> /lidar_points_nav
  -> Nav2 local VoxelLayer
```

`map -> lio_map` is published as an identity transform. This lets Nav2 keep its
standard `map` global frame while FAST-LIO keeps its internal `lio_map` frame.

## 2D Mapping

Start FAST-LIO, the 3D accumulator, and the 2D projection mapper:

```bash
cd /home/star/unitree-go2-fan
./scripts/fast_lio_2d_mapping.sh
```

Save the current 3D point cloud map:

```bash
ros2 service call /save_lio_cloud_map std_srvs/srv/Trigger '{}'
```

Save the projected 2D Nav2 map:

```bash
ros2 service call /save_lio_2d_map std_srvs/srv/Trigger '{}'
```

Default output directory:

```text
/home/star/go2_maps/fast_lio2/
```

The 2D map publisher keeps stable map bounds by default. The map can grow when
new space is discovered, but it will not shrink or jitter around the robot. This
keeps Nav2 from constantly resizing its global costmap.

## Projection Parameters

Useful launch parameters:

```bash
./scripts/fast_lio_2d_mapping.sh \
  grid_resolution:=0.05 \
  grid_obstacle_min_z:=0.18 \
  grid_obstacle_max_z:=1.60 \
  grid_obstacle_dilation_radius:=0.05
```

Useful stable-bound parameters:

```bash
./scripts/fast_lio_2d_mapping.sh \
  grid_stable_bounds:=true \
  grid_growth_margin:=2.0 \
  grid_bounds_snap:=1.0
```

If the 2D map looks too sparse, lower the 3D voxel size:

```bash
./scripts/fast_lio_2d_mapping.sh \
  lio_cloud_map_voxel_size:=0.05 \
  lio_cloud_map_max_points:=600000
```

If the floor is being marked as obstacles, raise `grid_obstacle_min_z`.
If low boxes or cables are missed, lower `grid_obstacle_min_z`.

## Experimental Nav2 Bring-Up

Dry-run Nav2 without sending velocity commands to the robot:

```bash
./scripts/fast_lio_nav2.sh
```

This starts FAST-LIO, the projected `/map`, Nav2, and RViz. It does not start
the Unitree sport command bridge by default.

Only after checking costmaps, TF, and planned paths:

```bash
./scripts/fast_lio_nav2.sh start_go2_cmd_bridge:=true
```

## Runtime Checks

Useful checks while the system is running:

```bash
ros2 topic hz /lidar_points
ros2 topic hz /imu_lio
ros2 topic hz /lio_odom
ros2 topic hz /map
ros2 run tf2_ros tf2_echo map base_link
```

Expected current ranges:

- `/lidar_points`: about 10 Hz from the Hesai driver
- `/imu_lio`: about 400 Hz after unit conversion and monotonic stamp guarding
- `/lio_odom`: hundreds of Hz from FAST-LIO
- `/map`: about 1 Hz from the 2D projection mapper

If FAST-LIO reports non-ascending IMU timestamps, check
`go2_lio_imu_adapter` stats. `corrected_output_stamps` can increase, but
FAST-LIO should not receive non-ascending output stamps.

If Nav2 repeatedly logs `StaticLayer: Resizing costmap`, check
`go2_lio_grid_mapper` stats. `bounds_expansions` should only increase when the
dog discovers new map area, not continuously while standing still.

## 2.5D Direction

The present implementation is a 2D projection from the 3D FAST-LIO map. The next
useful 2.5D step is to keep per-cell height statistics:

- minimum observed ground height
- maximum obstacle height
- height variance or slope proxy
- traversability cost derived from height discontinuity

That can be layered on top of the current `go2_lio_grid_mapper` without changing
FAST-LIO itself.
