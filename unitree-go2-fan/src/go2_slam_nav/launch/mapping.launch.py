from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.substitutions import Command, PathJoinSubstitution, LaunchConfiguration, PythonExpression
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        # Declare arguments for configuration
        DeclareLaunchArgument(
            name='use_rviz',
            default_value='true',
            choices=['true', 'false'],
            description='Open RVIZ for visualization'
        ),
        DeclareLaunchArgument(
            name='use_sim_time',
            default_value='false',
            choices=['true', 'false'],
            description='Use simulation clock if true'
        ),
        DeclareLaunchArgument(
            name='deskewing',
            default_value='false',
            choices=['true', 'false'],
            description='Enable RTAB-Map LiDAR deskewing'
        ),
        DeclareLaunchArgument(
            name='use_rtabmapviz',
            default_value='true',
            choices=['true', 'false'],
            description='Open RTAB-Map visualization'
        ),
        DeclareLaunchArgument(
            name='localize_only',
            default_value='false',
            choices=['true', 'false'],
            description='Localize only, do not add nodes to the RTAB-Map database'
        ),
        DeclareLaunchArgument(
            name='restart_map',
            default_value='true',
            choices=['true', 'false'],
            description='Delete previous map and restart'
        ),
        DeclareLaunchArgument(
            name='start_lidar_driver',
            default_value='true',
            choices=['true', 'false'],
            description='Start the Hesai LiDAR ROS2 driver from this launch file'
        ),
        DeclareLaunchArgument(
            name='hesai_config_path',
            default_value=PathJoinSubstitution([
                FindPackageShare('go2_slam_nav'),
                'config',
                'hesai_jt128.yaml'
            ]),
            description='Hesai driver config.yaml path'
        ),
        DeclareLaunchArgument(
            name='lidar_topic',
            default_value='/lidar_points',
            description='PointCloud2 topic published by Hesai JT128'
        ),
        DeclareLaunchArgument(
            name='icp_lidar_topic',
            default_value='/lidar_points_slam',
            description='Throttled PointCloud2 topic consumed by ICP odometry'
        ),
        DeclareLaunchArgument(
            name='use_lidar_throttle',
            default_value='true',
            choices=['true', 'false'],
            description='Throttle raw Hesai point clouds before RTAB-Map ICP odometry'
        ),
        DeclareLaunchArgument(
            name='lidar_throttle_rate',
            default_value='4.0',
            description='Maximum throttled LiDAR rate in Hz for ICP/RViz'
        ),
        DeclareLaunchArgument(
            name='lidar_point_stride',
            default_value='2',
            description='Keep one point every N raw LiDAR points before SLAM'
        ),
        DeclareLaunchArgument(
            name='rviz_lidar_topic',
            default_value='/lidar_points_viz',
            description='Lightweight PointCloud2 topic for RViz live display'
        ),
        DeclareLaunchArgument(
            name='rviz_lidar_throttle_rate',
            default_value='0.5',
            description='Maximum lightweight RViz LiDAR display rate in Hz'
        ),
        DeclareLaunchArgument(
            name='rviz_lidar_point_stride',
            default_value='12',
            description='Keep one point every N SLAM points for RViz display'
        ),
        DeclareLaunchArgument(
            name='publish_viz_clouds',
            default_value='false',
            choices=['true', 'false'],
            description='Publish lightweight visualization clouds even when this launch does not open RViz'
        ),
        DeclareLaunchArgument(
            name='cloud_map_viz_topic',
            default_value='/cloud_map_viz',
            description='Lightweight RTAB-Map cloud topic for RViz display'
        ),
        DeclareLaunchArgument(
            name='cloud_map_viz_throttle_rate',
            default_value='0.2',
            description='Maximum lightweight RTAB-Map cloud display rate in Hz'
        ),
        DeclareLaunchArgument(
            name='cloud_map_viz_point_stride',
            default_value='16',
            description='Keep one point every N /cloud_map points for RViz display'
        ),
        DeclareLaunchArgument(
            name='publish_visual_3d_map',
            default_value='true',
            choices=['true', 'false'],
            description='Publish an accumulated visual 3D cloud map for RViz demonstration'
        ),
        DeclareLaunchArgument(
            name='visual_3d_map_topic',
            default_value='/visual_cloud_map',
            description='Accumulated visual 3D cloud map topic for RViz'
        ),
        DeclareLaunchArgument(
            name='visual_3d_map_rate',
            default_value='0.5',
            description='Publish rate in Hz for the accumulated visual 3D cloud map'
        ),
        DeclareLaunchArgument(
            name='visual_3d_map_input_rate',
            default_value='1.0',
            description='Maximum input integration rate in Hz for the accumulated visual 3D cloud map'
        ),
        DeclareLaunchArgument(
            name='visual_3d_map_point_stride',
            default_value='4',
            description='Keep one point every N SLAM points for the accumulated visual 3D cloud map'
        ),
        DeclareLaunchArgument(
            name='visual_3d_map_voxel_size',
            default_value='0.08',
            description='Voxel size in meters used by the accumulated visual 3D cloud map'
        ),
        DeclareLaunchArgument(
            name='visual_3d_map_max_points',
            default_value='150000',
            description='Maximum retained voxels in the accumulated visual 3D cloud map'
        ),
        DeclareLaunchArgument(name='visual_3d_map_min_z', default_value='-0.40'),
        DeclareLaunchArgument(name='visual_3d_map_max_z', default_value='2.20'),
        DeclareLaunchArgument(name='visual_3d_map_min_range', default_value='0.20'),
        DeclareLaunchArgument(name='visual_3d_map_max_range', default_value='8.0'),
        DeclareLaunchArgument(
            name='lidar_throttle_stamp_mode',
            default_value='now',
            choices=['now', 'input'],
            description='Use current ROS time or original input timestamps on throttled clouds'
        ),
        DeclareLaunchArgument(
            name='slam_filter_enabled',
            default_value='true',
            choices=['true', 'false'],
            description='Filter self/ceiling/far points before RTAB-Map to reduce ghosting'
        ),
        DeclareLaunchArgument(name='slam_filter_min_z', default_value='-0.35'),
        DeclareLaunchArgument(name='slam_filter_max_z', default_value='1.80'),
        DeclareLaunchArgument(name='slam_filter_min_range', default_value='0.20'),
        DeclareLaunchArgument(name='slam_filter_max_range', default_value='6.0'),
        DeclareLaunchArgument(name='slam_self_filter_enabled', default_value='true'),
        DeclareLaunchArgument(name='slam_self_min_x', default_value='-0.65'),
        DeclareLaunchArgument(name='slam_self_max_x', default_value='0.60'),
        DeclareLaunchArgument(name='slam_self_min_y', default_value='-0.45'),
        DeclareLaunchArgument(name='slam_self_max_y', default_value='0.45'),
        DeclareLaunchArgument(name='slam_self_min_z', default_value='-0.50'),
        DeclareLaunchArgument(name='slam_self_max_z', default_value='0.80'),
        DeclareLaunchArgument(
            name='lidar_frame_id',
            default_value='hesai_lidar',
            description='Frame id used by Hesai point clouds'
        ),
        DeclareLaunchArgument(
            name='use_cloud_assembler',
            default_value='false',
            choices=['true', 'false'],
            description='Assemble ICP filtered clouds before RTAB-Map'
        ),
        DeclareLaunchArgument(
            name='rtabmap_scan_cloud_topic',
            default_value='/lidar_points_slam',
            description='PointCloud2 topic consumed by RTAB-Map after ICP odometry'
        ),
        DeclareLaunchArgument(
            name='odom_source',
            default_value='unitree',
            choices=['unitree', 'icp', 'ekf'],
            description='Use Go2 body odometry by default; pass ekf for Unitree odom + IMU fusion or icp for LiDAR-only bench tests'
        ),
        DeclareLaunchArgument(
            name='unitree_odom_topic',
            default_value='/utlidar/robot_odom',
            description='Unitree odometry topic used when odom_source is unitree'
        ),
        DeclareLaunchArgument(
            name='odom_topic',
            default_value='/odom',
            description='Odometry topic consumed by RTAB-Map/Nav2'
        ),
        DeclareLaunchArgument(
            name='ekf_odom_topic',
            default_value='/odom_unitree',
            description='Internal Unitree odometry topic consumed by robot_localization when odom_source is ekf'
        ),
        DeclareLaunchArgument(
            name='unitree_imu_topic',
            default_value='/utlidar/imu',
            description='Unitree IMU topic consumed by robot_localization when odom_source is ekf'
        ),
        DeclareLaunchArgument(
            name='publish_unitree_imu_tf',
            default_value='true',
            choices=['true', 'false'],
            description='Publish static base_link to Unitree IMU message frame transform'
        ),
        DeclareLaunchArgument(name='unitree_imu_tf_x', default_value='-0.026'),
        DeclareLaunchArgument(name='unitree_imu_tf_y', default_value='0.0'),
        DeclareLaunchArgument(name='unitree_imu_tf_z', default_value='0.042'),
        DeclareLaunchArgument(name='unitree_imu_tf_roll', default_value='0.0'),
        DeclareLaunchArgument(name='unitree_imu_tf_pitch', default_value='0.0'),
        DeclareLaunchArgument(name='unitree_imu_tf_yaw', default_value='0.0'),
        DeclareLaunchArgument(
            name='ekf_config_path',
            default_value=PathJoinSubstitution([
                FindPackageShare('go2_slam_nav'),
                'config',
                'ekf_unitree_imu.yaml'
            ]),
            description='robot_localization EKF config used when odom_source is ekf'
        ),
        DeclareLaunchArgument(
            name='publish_odom_tf',
            default_value='true',
            choices=['true', 'false'],
            description='Publish odom->base_link TF from the selected Unitree odometry'
        ),
        DeclareLaunchArgument(
            name='odom_relay_rate',
            default_value='30.0',
            description='Maximum Unitree odometry relay rate in Hz'
        ),
        DeclareLaunchArgument(
            name='odom_stamp_mode',
            default_value='now',
            choices=['now', 'input'],
            description='Use current ROS time or original input timestamps on relayed odometry'
        ),
        DeclareLaunchArgument(
            name='odom_flatten_to_2d',
            default_value='true',
            choices=['true', 'false'],
            description='Use only x/y/yaw from Unitree odometry for stable 2D/3D RTAB-Map bring-up'
        ),
        DeclareLaunchArgument(
            name='odom_replace_zero_covariance',
            default_value='false',
            choices=['true', 'false'],
            description='Replace all-zero Unitree odometry covariance before publishing'
        ),
        DeclareLaunchArgument(
            name='publish_static_tf',
            default_value='false',
            choices=['true', 'false'],
            description='Publish optional static base_link to RTAB-Map robot frame transform'
        ),
        DeclareLaunchArgument(
            name='publish_lidar_tf',
            default_value='true',
            choices=['true', 'false'],
            description='Publish static base_link to Hesai LiDAR transform'
        ),
        DeclareLaunchArgument(
            name='publish_go2_marker',
            default_value='true',
            choices=['true', 'false'],
            description='Publish a visible Go2 body marker in RViz'
        ),
        DeclareLaunchArgument(
            name='marker_publish_rate',
            default_value='5.0',
            description='Go2 RViz marker publish rate in Hz'
        ),
        DeclareLaunchArgument(
            name='use_go2_urdf',
            default_value='true',
            choices=['true', 'false'],
            description='Publish Go2 robot_description from a URDF for RViz RobotModel'
        ),
        DeclareLaunchArgument(
            name='go2_urdf_path',
            default_value=PathJoinSubstitution([
                FindPackageShare('go2_description'),
                'urdf',
                'go2_description.urdf'
            ]),
            description='Go2 URDF path used when use_go2_urdf is true'
        ),
        DeclareLaunchArgument(
            name='lidar_tf_x',
            default_value='0.0',
            description='LiDAR x offset from base_link in meters, positive forward'
        ),
        DeclareLaunchArgument(
            name='lidar_tf_y',
            default_value='0.0',
            description='LiDAR y offset from base_link in meters, positive left'
        ),
        DeclareLaunchArgument(
            name='lidar_tf_z',
            default_value='0.10',
            description='LiDAR z offset from base_link in meters, positive up'
        ),
        DeclareLaunchArgument(
            name='lidar_tf_roll',
            default_value='0.0',
            description='LiDAR roll relative to base_link in radians'
        ),
        DeclareLaunchArgument(
            name='lidar_tf_pitch',
            default_value='0.0',
            description='LiDAR pitch relative to base_link in radians'
        ),
        DeclareLaunchArgument(
            name='lidar_tf_yaw',
            default_value='0.0',
            description=(
                'JT128 mounting yaw relative to base_link; forward mounting is zero'
            )
        ),
        DeclareLaunchArgument(
            name='odom_align_with_ground',
            default_value='false',
            choices=['true', 'false'],
            description='Align ICP odometry with detected ground on initialization'
        ),
        DeclareLaunchArgument(
            name='icp_range_max',
            default_value='12.0',
            description='Maximum LiDAR range used by ICP odometry'
        ),
        DeclareLaunchArgument(
            name='rtabmap_voxel_size',
            default_value='0.12',
            description='C++ voxel size used by RTAB-Map ICP/grid processing'
        ),
        DeclareLaunchArgument(
            name='icp_expected_update_rate',
            default_value='10.0',
            description='Expected throttled LiDAR rate. Keep this higher than lidar_throttle_rate'
        ),
        DeclareLaunchArgument(
            name='icp_max_update_rate',
            default_value='6.0',
            description='Maximum ICP odometry processing rate in Hz'
        ),
        DeclareLaunchArgument(
            name='icp_max_translation',
            default_value='0.45',
            description='Maximum per-update ICP translation accepted in meters'
        ),
        DeclareLaunchArgument(
            name='icp_max_rotation',
            default_value='0.78',
            description='Maximum per-update ICP rotation accepted in radians'
        ),
        DeclareLaunchArgument(
            name='icp_max_correspondence_distance',
            default_value='0.35',
            description='Maximum ICP correspondence distance in meters'
        ),
        DeclareLaunchArgument(
            name='icp_correspondence_ratio',
            default_value='0.08',
            description='Minimum matching correspondence ratio required by ICP odometry'
        ),
        DeclareLaunchArgument(
            name='icp_outlier_ratio',
            default_value='0.65',
            description='Trimmed outlier ratio used by libpointmatcher ICP'
        ),
        DeclareLaunchArgument(
            name='icp_force_4dof',
            default_value='true',
            choices=['true', 'false'],
            description='Limit ICP correction to x/y/z/yaw'
        ),
        DeclareLaunchArgument(
            name='icp_point_to_plane_min_complexity',
            default_value='0.02',
            description='Minimum point-to-plane scene complexity'
        ),
        DeclareLaunchArgument(
            name='odom_filtering_strategy',
            default_value='1',
            description='Odometry smoothing: 0 none, 1 Kalman, 2 particle'
        ),
        DeclareLaunchArgument(
            name='odom_guess_smoothing_delay',
            default_value='0.0',
            description='Seconds used to smooth the motion guess from previous odometry'
        ),
        DeclareLaunchArgument(
            name='odom_holonomic',
            default_value='true',
            choices=['true', 'false'],
            description='Whether odometry can estimate lateral motion independently'
        ),
        DeclareLaunchArgument(
            name='enable_loop_closure',
            default_value='false',
            choices=['true', 'false'],
            description='Enable RTAB-Map proximity loop closures'
        ),
        DeclareLaunchArgument(
            name='rtabmap_optimize_from_graph_end',
            default_value='true',
            choices=['true', 'false'],
            description='Optimize graph from the latest node to reduce robot pose jumps'
        ),
        DeclareLaunchArgument(
            name='rtabmap_optimize_max_error',
            default_value='2.0',
            description='Reject loop closures when graph optimization error ratio is too high'
        ),
        DeclareLaunchArgument(
            name='grid_range_max',
            default_value='5.5',
            description='Maximum LiDAR range used for RTAB-Map occupancy grid'
        ),
        DeclareLaunchArgument(
            name='grid_max_obstacle_height',
            default_value='1.2',
            description='Maximum obstacle height kept in the 2D occupancy grid'
        ),
        DeclareLaunchArgument(
            name='grid_min_cluster_size',
            default_value='25',
            description='Minimum RTAB-Map obstacle cluster size projected into the grid'
        ),
        DeclareLaunchArgument(
            name='grid_flat_obstacles',
            default_value='false',
            choices=['true', 'false'],
            description='Detect flat horizontal surfaces as obstacles in the occupancy grid'
        ),
        DeclareLaunchArgument(
            name='grid_noise_filtering_radius',
            default_value='0.25',
            description='Radius for RTAB-Map occupancy grid noise filtering'
        ),
        DeclareLaunchArgument(
            name='grid_noise_filtering_min_neighbors',
            default_value='10',
            description='Minimum neighbors for RTAB-Map occupancy grid noise filtering'
        ),
        DeclareLaunchArgument(
            name='rtabmap_linear_update',
            default_value='0.12',
            description='Minimum linear motion in meters before RTAB-Map inserts a new node'
        ),
        DeclareLaunchArgument(
            name='rtabmap_angular_update',
            default_value='0.12',
            description='Minimum angular motion in radians before RTAB-Map inserts a new node'
        ),
        DeclareLaunchArgument(
            name='odom_scan_keyframe_thr',
            default_value='0.75',
            description='ICP odometry scan keyframe threshold; higher values reduce duplicate local map inserts'
        ),
        DeclareLaunchArgument(
            name='odom_scan_subtract_radius',
            default_value='0.20',
            description='Radius used to merge similar ICP local-map points'
        ),
        DeclareLaunchArgument(
            name='odom_scan_max_size',
            default_value='8000',
            description='Maximum points kept in the ICP odometry local scan map'
        ),

        # Start Hesai JT128 driver. The driver config publishes /lidar_points by default.
        Node(
            package='hesai_ros_driver',
            executable='hesai_ros_driver_node',
            output='screen',
            parameters=[{
                'config_path': LaunchConfiguration('hesai_config_path')
            }],
            condition=IfCondition(LaunchConfiguration('start_lidar_driver')),
        ),

        Node(
            package='rviz2',
            executable='rviz2',
            arguments=[
                '-d',
                PathJoinSubstitution([
                    FindPackageShare('go2_slam_nav'),
                    'config',
                    'nav.rviz'
                ])
            ],
            condition=IfCondition(LaunchConfiguration('use_rviz')),
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_marker_publisher',
            name='go2_marker_publisher',
            output='screen',
            parameters=[{
                'frame_id': 'base_link',
                'topic': '/go2_marker',
                'publish_rate': LaunchConfiguration('marker_publish_rate'),
            }],
            condition=IfCondition(LaunchConfiguration('publish_go2_marker')),
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_cloud_throttle',
            name='go2_cloud_throttle',
            output='screen',
            parameters=[{
                'input_topic': LaunchConfiguration('lidar_topic'),
                'output_topic': LaunchConfiguration('icp_lidar_topic'),
                'max_rate': LaunchConfiguration('lidar_throttle_rate'),
                'stamp_mode': LaunchConfiguration('lidar_throttle_stamp_mode'),
                'point_stride': LaunchConfiguration('lidar_point_stride'),
                'filter_enabled': LaunchConfiguration('slam_filter_enabled'),
                'min_z': LaunchConfiguration('slam_filter_min_z'),
                'max_z': LaunchConfiguration('slam_filter_max_z'),
                'min_range': LaunchConfiguration('slam_filter_min_range'),
                'max_range': LaunchConfiguration('slam_filter_max_range'),
                'self_filter_enabled': LaunchConfiguration('slam_self_filter_enabled'),
                'self_min_x': LaunchConfiguration('slam_self_min_x'),
                'self_max_x': LaunchConfiguration('slam_self_max_x'),
                'self_min_y': LaunchConfiguration('slam_self_min_y'),
                'self_max_y': LaunchConfiguration('slam_self_max_y'),
                'self_min_z': LaunchConfiguration('slam_self_min_z'),
                'self_max_z': LaunchConfiguration('slam_self_max_z'),
            }],
            condition=IfCondition(LaunchConfiguration('use_lidar_throttle')),
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_cloud_throttle',
            name='go2_cloud_viz_throttle',
            output='screen',
            parameters=[{
                'input_topic': PythonExpression([
                    '"', LaunchConfiguration('icp_lidar_topic'),
                    '" if "', LaunchConfiguration('use_lidar_throttle'),
                    '" == "true" else "', LaunchConfiguration('lidar_topic'), '"'
                ]),
                'output_topic': LaunchConfiguration('rviz_lidar_topic'),
                'max_rate': LaunchConfiguration('rviz_lidar_throttle_rate'),
                'stamp_mode': LaunchConfiguration('lidar_throttle_stamp_mode'),
                'point_stride': LaunchConfiguration('rviz_lidar_point_stride'),
                'filter_enabled': False,
                'self_filter_enabled': False,
                'require_subscriber': True,
            }],
            condition=IfCondition(LaunchConfiguration('publish_viz_clouds')),
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_cloud_throttle',
            name='go2_cloud_map_viz_throttle',
            output='screen',
            parameters=[{
                'input_topic': '/cloud_map',
                'output_topic': LaunchConfiguration('cloud_map_viz_topic'),
                'max_rate': LaunchConfiguration('cloud_map_viz_throttle_rate'),
                'stamp_mode': 'now',
                'point_stride': LaunchConfiguration('cloud_map_viz_point_stride'),
                'filter_enabled': False,
                'self_filter_enabled': False,
                'require_subscriber': True,
            }],
            condition=IfCondition(LaunchConfiguration('publish_viz_clouds')),
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_cloud_accumulator',
            name='go2_visual_cloud_accumulator',
            output='screen',
            parameters=[{
                'input_topic': PythonExpression([
                    '"', LaunchConfiguration('icp_lidar_topic'),
                    '" if "', LaunchConfiguration('use_lidar_throttle'),
                    '" == "true" else "', LaunchConfiguration('lidar_topic'), '"'
                ]),
                'output_topic': LaunchConfiguration('visual_3d_map_topic'),
                'target_frame': 'map',
                'max_input_rate': LaunchConfiguration('visual_3d_map_input_rate'),
                'publish_rate': LaunchConfiguration('visual_3d_map_rate'),
                'point_stride': LaunchConfiguration('visual_3d_map_point_stride'),
                'voxel_size': LaunchConfiguration('visual_3d_map_voxel_size'),
                'max_points': LaunchConfiguration('visual_3d_map_max_points'),
                'min_z': LaunchConfiguration('visual_3d_map_min_z'),
                'max_z': LaunchConfiguration('visual_3d_map_max_z'),
                'min_range': LaunchConfiguration('visual_3d_map_min_range'),
                'max_range': LaunchConfiguration('visual_3d_map_max_range'),
            }],
            condition=IfCondition(PythonExpression([
                '"', LaunchConfiguration('publish_viz_clouds'), '" == "true" and "',
                LaunchConfiguration('publish_visual_3d_map'), '" == "true"'
            ])),
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_odom_relay',
            name='go2_odom_relay',
            output='screen',
            parameters=[{
                'input_topic': LaunchConfiguration('unitree_odom_topic'),
                'output_topic': PythonExpression([
                    '"', LaunchConfiguration('ekf_odom_topic'),
                    '" if "', LaunchConfiguration('odom_source'),
                    '" == "ekf" else "', LaunchConfiguration('odom_topic'), '"'
                ]),
                'odom_frame_id': 'odom',
                'base_frame_id': 'base_link',
                'publish_tf': PythonExpression([
                    '"false" if "', LaunchConfiguration('odom_source'),
                    '" == "ekf" else "', LaunchConfiguration('publish_odom_tf'), '"'
                ]),
                'max_rate': LaunchConfiguration('odom_relay_rate'),
                'stamp_mode': LaunchConfiguration('odom_stamp_mode'),
                'flatten_to_2d': LaunchConfiguration('odom_flatten_to_2d'),
                'replace_zero_covariance': PythonExpression([
                    '"true" if "', LaunchConfiguration('odom_source'),
                    '" == "ekf" else "', LaunchConfiguration('odom_replace_zero_covariance'), '"'
                ]),
            }],
            condition=IfCondition(PythonExpression([
                '"', LaunchConfiguration('odom_source'), '" in ("unitree", "ekf")'
            ])),
        ),

        Node(
            package='robot_localization',
            executable='ekf_node',
            name='go2_ekf_localization',
            output='screen',
            parameters=[
                LaunchConfiguration('ekf_config_path'),
                {'use_sim_time': LaunchConfiguration('use_sim_time')},
            ],
            remappings=[
                ('odometry/filtered', LaunchConfiguration('odom_topic')),
                ('/odom_unitree', LaunchConfiguration('ekf_odom_topic')),
                ('/utlidar/imu', LaunchConfiguration('unitree_imu_topic')),
            ],
            condition=IfCondition(PythonExpression([
                '"', LaunchConfiguration('odom_source'), '" == "ekf"'
            ])),
        ),

        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            arguments=[
                '--x', LaunchConfiguration('unitree_imu_tf_x'),
                '--y', LaunchConfiguration('unitree_imu_tf_y'),
                '--z', LaunchConfiguration('unitree_imu_tf_z'),
                '--roll', LaunchConfiguration('unitree_imu_tf_roll'),
                '--pitch', LaunchConfiguration('unitree_imu_tf_pitch'),
                '--yaw', LaunchConfiguration('unitree_imu_tf_yaw'),
                '--frame-id', 'base_link',
                '--child-frame-id', 'utlidar_imu',
            ],
            condition=IfCondition(LaunchConfiguration('publish_unitree_imu_tf')),
        ),

        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='go2_robot_state_publisher',
            output='screen',
            parameters=[{
                'robot_description': ParameterValue(
                    Command(['cat ', LaunchConfiguration('go2_urdf_path')]),
                    value_type=str,
                ),
                'use_sim_time': LaunchConfiguration('use_sim_time'),
            }],
            condition=IfCondition(LaunchConfiguration('use_go2_urdf')),
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_joint_state_publisher',
            name='go2_joint_state_publisher',
            output='screen',
            condition=IfCondition(LaunchConfiguration('use_go2_urdf')),
        ),

        # Include RTAB-Map LiDAR mapping pipeline.
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('go2_slam_nav'),
                    'launch',
                    'rtab_lidar.launch.py'
                ])
            ),
            launch_arguments=[
                ('use_sim_time', LaunchConfiguration('use_sim_time')),
                ('deskewing', LaunchConfiguration('deskewing')),
                ('use_rtabmapviz', LaunchConfiguration('use_rtabmapviz')),
                ('localize_only', LaunchConfiguration('localize_only')),
                ('restart_map', LaunchConfiguration('restart_map')),
                ('lidar_topic', PythonExpression([
                    '"', LaunchConfiguration('icp_lidar_topic'),
                    '" if "', LaunchConfiguration('use_lidar_throttle'),
                    '" == "true" else "', LaunchConfiguration('lidar_topic'), '"'
                ])),
                ('lidar_frame_id', LaunchConfiguration('lidar_frame_id')),
                ('odom_source', LaunchConfiguration('odom_source')),
                ('odom_topic', LaunchConfiguration('odom_topic')),
                ('use_cloud_assembler', LaunchConfiguration('use_cloud_assembler')),
                ('rtabmap_scan_cloud_topic', LaunchConfiguration('rtabmap_scan_cloud_topic')),
                ('publish_static_tf', LaunchConfiguration('publish_static_tf')),
                ('publish_lidar_tf', LaunchConfiguration('publish_lidar_tf')),
                ('lidar_tf_x', LaunchConfiguration('lidar_tf_x')),
                ('lidar_tf_y', LaunchConfiguration('lidar_tf_y')),
                ('lidar_tf_z', LaunchConfiguration('lidar_tf_z')),
                ('lidar_tf_roll', LaunchConfiguration('lidar_tf_roll')),
                ('lidar_tf_pitch', LaunchConfiguration('lidar_tf_pitch')),
                ('lidar_tf_yaw', LaunchConfiguration('lidar_tf_yaw')),
                ('odom_align_with_ground', LaunchConfiguration('odom_align_with_ground')),
                ('icp_range_max', LaunchConfiguration('icp_range_max')),
                ('rtabmap_voxel_size', LaunchConfiguration('rtabmap_voxel_size')),
                ('icp_expected_update_rate', LaunchConfiguration('icp_expected_update_rate')),
                ('icp_max_update_rate', LaunchConfiguration('icp_max_update_rate')),
                ('icp_max_translation', LaunchConfiguration('icp_max_translation')),
                ('icp_max_rotation', LaunchConfiguration('icp_max_rotation')),
                ('icp_max_correspondence_distance', LaunchConfiguration('icp_max_correspondence_distance')),
                ('icp_correspondence_ratio', LaunchConfiguration('icp_correspondence_ratio')),
                ('icp_outlier_ratio', LaunchConfiguration('icp_outlier_ratio')),
                ('icp_force_4dof', LaunchConfiguration('icp_force_4dof')),
                ('icp_point_to_plane_min_complexity', LaunchConfiguration('icp_point_to_plane_min_complexity')),
                ('odom_filtering_strategy', LaunchConfiguration('odom_filtering_strategy')),
                ('odom_guess_smoothing_delay', LaunchConfiguration('odom_guess_smoothing_delay')),
                ('odom_holonomic', LaunchConfiguration('odom_holonomic')),
                ('odom_scan_keyframe_thr', LaunchConfiguration('odom_scan_keyframe_thr')),
                ('odom_scan_subtract_radius', LaunchConfiguration('odom_scan_subtract_radius')),
                ('odom_scan_max_size', LaunchConfiguration('odom_scan_max_size')),
                ('enable_loop_closure', LaunchConfiguration('enable_loop_closure')),
                ('rtabmap_linear_update', LaunchConfiguration('rtabmap_linear_update')),
                ('rtabmap_angular_update', LaunchConfiguration('rtabmap_angular_update')),
                ('rtabmap_optimize_from_graph_end', LaunchConfiguration('rtabmap_optimize_from_graph_end')),
                ('rtabmap_optimize_max_error', LaunchConfiguration('rtabmap_optimize_max_error')),
                ('grid_range_max', LaunchConfiguration('grid_range_max')),
                ('grid_max_obstacle_height', LaunchConfiguration('grid_max_obstacle_height')),
                ('grid_min_cluster_size', LaunchConfiguration('grid_min_cluster_size')),
                ('grid_flat_obstacles', LaunchConfiguration('grid_flat_obstacles')),
                ('grid_noise_filtering_radius', LaunchConfiguration('grid_noise_filtering_radius')),
                ('grid_noise_filtering_min_neighbors', LaunchConfiguration('grid_noise_filtering_min_neighbors')),
            ],
        ),
    ])
