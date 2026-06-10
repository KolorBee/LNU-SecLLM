# Third-Party Notices

This workspace currently bundles or derives work from the following local sources:

- `/home/star/unitree-go2-slam-nav2`
  - Local packages copied: `go2_slam_nav`, `go2_cmd_processor`.
  - These packages were adapted for Hesai JT128, RTAB-Map LiDAR mapping, Go2 visualization, and Nav2 integration.

- `/home/star/go2-nav2-amcl`
  - Local package copied: `go2_description`.
  - Used for Go2 URDF and mesh assets.

- `/home/star/hesai_ws/src/HesaiLidar_ROS_2.0`
  - Local package copied: `HesaiLidar_ROS_2.0`.
  - Upstream project: HesaiTechnology/HesaiLidar_ROS_2.0.
  - Its upstream `LICENSE` file is preserved inside `src/HesaiLidar_ROS_2.0/LICENSE`.

Before publishing this repository publicly, audit every copied package license. Do not remove upstream copyright,
license, or attribution notices.
