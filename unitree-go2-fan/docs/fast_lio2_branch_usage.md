# FAST-LIO2 Branch Usage

This branch is a project-local FAST-LIO2 integration for Unitree Go2 and Hesai
JT128. It does not replace the current RTAB-Map mapping launch by default. It
adds the sensor-side contract and starts the installed `spark_fast_lio` core:

```text
/lidar_points  -> go2_lio_points_adapter -> /points_raw -> spark_fast_lio
/utlidar/imu   -> go2_lio_imu_adapter    -> /imu_lio    -> spark_fast_lio
base_link      -> hesai_lidar             static TF
base_link      -> utlidar_imu             static TF
spark_fast_lio -> /lio_odom, /lio_path, /lio_cloud_registered, TF lio_map->base_link
```

## Why This Branch Exists

The current RTAB-Map path is stable enough for mapping and Nav2 bring-up, but
it is still a transition platform. For mine-tunnel inspection, a LiDAR-inertial
odometry front-end is a better long-term odometry source than pure LiDAR ICP.

This branch now uses `MIT-SPARK/spark-fast-lio`, installed under
`src/spark-fast-lio`. The first pass only validated adapted point cloud and IMU
topics; the current pass builds and launches the actual LIO core.

## Launch

```bash
cd /home/star/unitree-go2-fan
./scripts/lio_mapping.sh
```

Equivalent:

```bash
ros2 launch go2_slam_nav fast_lio2.launch.py \
  use_rviz:=true \
  start_lidar_driver:=true \
  start_fast_lio_core:=true
```

If `setup_go2.sh` pins CycloneDDS to `eno1` while `eno1` is DOWN, the helper
script automatically unsets `CYCLONEDDS_URI` for this local LIO bring-up. To
force the original Unitree DDS configuration, run:

```bash
UNITREE_GO2_FAN_KEEP_CYCLONEDDS_URI=1 ./scripts/lio_mapping.sh
```

Headless:

```bash
ros2 launch go2_slam_nav fast_lio2.launch.py \
  use_rviz:=false \
  start_lidar_driver:=true \
  start_fast_lio_core:=true
```

## Expected Topics

```text
/lidar_points             Raw Hesai point cloud
/points_raw               FAST-LIO2-oriented point cloud
/utlidar/imu              Unitree IMU
/imu_lio                  FAST-LIO2-oriented IMU
/odom_unitree_reference   Unitree odom reference, for comparison only
/lio_odom                 FAST-LIO2 odometry output
/lio_path                 FAST-LIO2 path output
/lio_cloud_registered     FAST-LIO2 registered cloud output
```

The adapter publishes `/points_raw` with these fields:

```text
x, y, z:       float32
intensity:     float32
ring:          uint16
time:          float32, seconds in scan
offset_time:   float32, seconds in scan
```

Live adapter validation on 2026-06-03 showed:

```text
/lidar_points raw width:       about 115072 points/frame
/points_raw adapted width:     about 81694 points/frame with default filters
/imu_lio rate:                 about 250 Hz
/points_raw adapter rate:      about 4 Hz, matching the current Hesai stream
```

The default point count reduction comes from z/range filtering, not from
`point_stride`. For maximum detail during algorithm testing:

```bash
./scripts/lio_mapping.sh lio_points_filter_enabled:=false
```

If Hesai does not provide ring/time fields, the adapter infers ring from
vertical angle and synthesizes time from point order and `lio_scan_period`.
This is enough for bring-up, but production FAST-LIO2 should use the driver's
best available per-point timing.

## Current Parameters

```text
lio_points_topic:=/points_raw
lio_imu_topic:=/imu_lio
lio_points_max_rate:=10.0
lio_points_stride:=1
lio_scan_period:=0.1
lio_points_filter_enabled:=true
lio_points_min_range:=0.20
lio_points_max_range:=80.0
lio_points_min_z:=-2.0
lio_points_max_z:=3.0
lidar_tf_z:=0.10
lidar_tf_yaw:=1.5707963268
unitree_imu_tf_yaw:=0.0
```

The default FAST-LIO2 LiDAR mounting guess is now:

```text
base_link -> hesai_lidar: x=0, y=0, z=0.10, yaw=+90 deg
base_link -> utlidar_imu: x=0, y=0, z=0, yaw=0 deg
FAST-LIO2 internal LiDAR -> Unitree IMU rotation: yaw=+90 deg
```

After fixing the `spark_fast_lio` base-pose math, the temporary `-90 deg`
Unitree IMU yaw compensation is no longer used. The current clean baseline
treats the Unitree IMU axes as aligned with `base_link`, matching the Go2 URDF.

If the robot still flies away while turning, do not re-add the temporary IMU yaw
compensation first. The next calibration test should flip the LiDAR yaw/extrinsic
pair together:

```bash
./scripts/lio_mapping.sh lidar_tf_yaw:=-1.5707963268
```

The project-local `spark_fast_lio` source has also been patched so
`common.visualization_frame: base` publishes `lio_map -> base_link` as:

```text
T_lio_map_base = T_lio_map_imu * T_imu_base
```

Earlier code used a conjugation-style rotation that could cancel yaw extrinsics,
making RViz look unchanged after 90/180 degree calibration changes and making
registered clouds inconsistent with the published base pose.

If the computer becomes sluggish:

```bash
./scripts/lio_mapping.sh lio_points_stride:=2 lio_points_max_rate:=5.0
```

Live core validation on 2026-06-03 showed:

```text
/lio_odom:              about 250 Hz
/lio_cloud_registered:  about 3.7 Hz
output frame:           lio_map
```

Do not publish another `odom -> base_link` while the RTAB-Map/Nav2 default
chain is running. Only one node should own a given TF edge.

## Important Bring-Up Choices

The Hesai raw `timestamp` field did not span a complete 0.1 s scan in the first
live test. For this LIO launch, the point adapter therefore uses synthesized
per-scan relative time by default:

```text
lio_points_use_input_time_field:=false
lio_scan_period:=0.1
```

The Unitree IMU header stamps were on a different time base from the Hesai
clouds in live testing. For this LIO launch, the IMU adapter therefore restamps
IMU messages on receipt:

```text
lio_imu_stamp_mode:=now
```

`spark_fast_lio` gravity alignment was also disabled for static bring-up:

```text
gravity_alignment.enable_gravity_alignment: false
```

## Validation Commands

```bash
ros2 topic hz /points_raw
ros2 topic echo /points_raw --once --field fields
ros2 topic hz /imu_lio
ros2 run tf2_ros tf2_echo base_link hesai_lidar
ros2 run tf2_ros tf2_echo base_link utlidar_imu
```

Once an external FAST-LIO2 core is installed:

```bash
ros2 topic hz /lio_odom
ros2 topic hz /lio_cloud_registered
ros2 run tf2_ros tf2_echo lio_odom base_link
```

## Important Limitation

Using the Unitree body IMU is a temporary bring-up step. FAST-LIO2 works best
when the IMU is rigidly mounted with the LiDAR. If the Go2 body shakes while the
LiDAR mount is not perfectly rigid, extrinsic and motion consistency will be
weaker than a true LiDAR-IMU module.
