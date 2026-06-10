from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([

        # ============ Launch Arguments ============
        DeclareLaunchArgument(
            name='use_sim_time',
            default_value='false',
            choices=['true','false'],
            description='Use simulation (Gazebo) clock if true'
        ),
        DeclareLaunchArgument(
            name='deskewing',
            default_value='false',
            choices=['true','false'],
            description='Enable lidar deskewing'
        ),
        DeclareLaunchArgument(
            name='localize_only',
            default_value='true',
            choices=['true','false'],
            description='Localize only, do not add new places to the map'
        ),
        DeclareLaunchArgument(
            name='restart_map',
            default_value='false',
            choices=['true','false'],
            description='Delete previous map/database and restart'
        ),
        DeclareLaunchArgument(
            name='use_rtabmapviz',
            default_value='true',
            choices=['true','false'],
            description='Start rtabmapviz node'
        ),
        DeclareLaunchArgument(
            name='rtabmap_log_level',
            default_value='WARN',
            choices=['ERROR', 'WARN', 'INFO', 'DEBUG'],
            description='Set logger level for rtabmap.'
        ),
        DeclareLaunchArgument(
            name='icp_odometry_log_level',
            default_value='WARN',
            choices=['ERROR', 'WARN', 'INFO', 'DEBUG'],
            description='Set logger level for icp_odometry.'
        ),
        DeclareLaunchArgument(
            name='lidar_topic',
            default_value='/lidar_points_slam',
            description='PointCloud2 topic published by the external LiDAR driver.'
        ),
        DeclareLaunchArgument(
            name='use_cloud_assembler',
            default_value='false',
            choices=['true','false'],
            description='Assemble ICP filtered clouds before RTAB-Map. Disabled by default for JT128 bring-up.'
        ),
        DeclareLaunchArgument(
            name='rtabmap_scan_cloud_topic',
            default_value='/lidar_points_slam',
            description='PointCloud2 topic consumed by RTAB-Map after ICP odometry.'
        ),
        DeclareLaunchArgument(
            name='odom_source',
            default_value='unitree',
            choices=['unitree', 'icp', 'ekf'],
            description='Use Unitree odometry, Unitree+IMU EKF odometry, or RTAB-Map ICP odometry for odom.'
        ),
        DeclareLaunchArgument(
            name='odom_topic',
            default_value='/odom',
            description='Odometry topic consumed by RTAB-Map.'
        ),
        DeclareLaunchArgument(
            name='base_frame_id',
            default_value='base_link',
            description='Robot base frame used by ICP odometry.'
        ),
        DeclareLaunchArgument(
            name='odom_frame_id',
            default_value='odom',
            description='Odometry frame published by ICP odometry.'
        ),
        DeclareLaunchArgument(
            name='rtabmap_frame_id',
            default_value='base_link',
            description='Robot frame used by RTAB-Map.'
        ),
        DeclareLaunchArgument(
            name='lidar_frame_id',
            default_value='hesai_lidar',
            description='Frame id in the Hesai PointCloud2 messages.'
        ),
        DeclareLaunchArgument(
            name='publish_static_tf',
            default_value='false',
            choices=['true','false'],
            description='Publish static base_link to RTAB-Map frame transform.'
        ),
        DeclareLaunchArgument(
            name='publish_lidar_tf',
            default_value='true',
            choices=['true','false'],
            description='Publish static base_link to LiDAR frame transform.'
        ),
        DeclareLaunchArgument(name='rtabmap_frame_x', default_value='0.0'),
        DeclareLaunchArgument(name='rtabmap_frame_y', default_value='0.0'),
        DeclareLaunchArgument(name='rtabmap_frame_z', default_value='0.2'),
        DeclareLaunchArgument(name='rtabmap_frame_roll', default_value='0.0'),
        DeclareLaunchArgument(name='rtabmap_frame_pitch', default_value='0.0'),
        DeclareLaunchArgument(name='rtabmap_frame_yaw', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_x', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_y', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_z', default_value='0.10'),
        DeclareLaunchArgument(name='lidar_tf_roll', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_pitch', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_yaw', default_value='0.0'),
        DeclareLaunchArgument(
            name='odom_align_with_ground',
            default_value='false',
            choices=['true','false'],
            description='Align ICP odometry with the detected ground on initialization.'
        ),
        DeclareLaunchArgument(
            name='icp_range_max',
            default_value='12.0',
            description='Maximum LiDAR range used by ICP odometry. 0 disables range filtering.'
        ),
        DeclareLaunchArgument(
            name='rtabmap_voxel_size',
            default_value='0.15',
            description='Voxel size used by RTAB-Map ICP/grid processing.'
        ),
        DeclareLaunchArgument(
            name='icp_expected_update_rate',
            default_value='10.0',
            description='Expected throttled LiDAR rate. Keep this higher than lidar_throttle_rate.'
        ),
        DeclareLaunchArgument(
            name='icp_max_update_rate',
            default_value='6.0',
            description='Maximum ICP odometry processing rate in Hz.'
        ),
        DeclareLaunchArgument(
            name='icp_max_translation',
            default_value='0.30',
            description='Maximum per-update ICP translation accepted in meters; rejects odometry jumps.'
        ),
        DeclareLaunchArgument(
            name='icp_max_rotation',
            default_value='0.30',
            description='Maximum per-update ICP rotation accepted in radians; rejects odometry jumps.'
        ),
        DeclareLaunchArgument(
            name='icp_max_correspondence_distance',
            default_value='0.35',
            description='Maximum ICP correspondence distance in meters.'
        ),
        DeclareLaunchArgument(
            name='icp_correspondence_ratio',
            default_value='0.08',
            description='Minimum matching correspondence ratio required by ICP odometry.'
        ),
        DeclareLaunchArgument(
            name='icp_outlier_ratio',
            default_value='0.65',
            description='Trimmed outlier ratio used by libpointmatcher ICP.'
        ),
        DeclareLaunchArgument(
            name='icp_force_4dof',
            default_value='true',
            choices=['true','false'],
            description='Limit ICP correction to x/y/z/yaw to avoid roll/pitch jumps on flat-floor bring-up.'
        ),
        DeclareLaunchArgument(
            name='icp_point_to_plane_min_complexity',
            default_value='0.05',
            description='Reject or constrain point-to-plane ICP when scene geometry is too degenerate.'
        ),
        DeclareLaunchArgument(
            name='odom_filtering_strategy',
            default_value='1',
            description='Odometry smoothing: 0 none, 1 Kalman, 2 particle.'
        ),
        DeclareLaunchArgument(
            name='odom_guess_smoothing_delay',
            default_value='0.3',
            description='Seconds used to smooth the motion guess from previous odometry.'
        ),
        DeclareLaunchArgument(
            name='odom_holonomic',
            default_value='true',
            choices=['true','false'],
            description='Whether odometry can estimate lateral motion independently.'
        ),
        DeclareLaunchArgument(
            name='odom_scan_keyframe_thr',
            default_value='0.75',
            description='ICP odometry scan keyframe threshold; higher values reduce duplicate local map inserts.'
        ),
        DeclareLaunchArgument(
            name='odom_scan_subtract_radius',
            default_value='0.20',
            description='Radius used to merge similar ICP local-map points.'
        ),
        DeclareLaunchArgument(
            name='odom_scan_max_size',
            default_value='8000',
            description='Maximum points kept in the ICP odometry local scan map.'
        ),
        DeclareLaunchArgument(
            name='enable_loop_closure',
            default_value='false',
            choices=['true','false'],
            description='Enable RTAB-Map proximity loop closures. Disabled by default during raw mapping bring-up to avoid false teleports.'
        ),
        DeclareLaunchArgument(
            name='rtabmap_linear_update',
            default_value='0.12',
            description='Minimum linear motion in meters before RTAB-Map inserts a new node.'
        ),
        DeclareLaunchArgument(
            name='rtabmap_angular_update',
            default_value='0.12',
            description='Minimum angular motion in radians before RTAB-Map inserts a new node.'
        ),
        DeclareLaunchArgument(
            name='rtabmap_optimize_from_graph_end',
            default_value='true',
            choices=['true','false'],
            description='Optimize graph from the latest node to reduce robot pose jumps in RViz.'
        ),
        DeclareLaunchArgument(
            name='rtabmap_optimize_max_error',
            default_value='2.0',
            description='Reject loop closures when graph optimization error ratio is too high.'
        ),
        DeclareLaunchArgument(
            name='grid_range_max',
            default_value='5.5',
            description='Maximum LiDAR range used when RTAB-Map creates the occupancy grid.'
        ),
        DeclareLaunchArgument(
            name='grid_max_obstacle_height',
            default_value='1.2',
            description='Maximum obstacle height kept in the 2D occupancy grid; lower it to reject ceiling points.'
        ),
        DeclareLaunchArgument(
            name='grid_min_cluster_size',
            default_value='25',
            description='Minimum obstacle cluster size projected into the RTAB-Map occupancy grid.'
        ),
        DeclareLaunchArgument(
            name='grid_flat_obstacles',
            default_value='false',
            choices=['true','false'],
            description='Detect flat horizontal surfaces as obstacles in the occupancy grid.'
        ),
        DeclareLaunchArgument(
            name='grid_noise_filtering_radius',
            default_value='0.25',
            description='Radius for RTAB-Map occupancy grid noise filtering. 0 disables it.'
        ),
        DeclareLaunchArgument(
            name='grid_noise_filtering_min_neighbors',
            default_value='10',
            description='Minimum neighbors for RTAB-Map occupancy grid noise filtering.'
        ),

        # ============ ICP Odometry Node ============
        Node(
            package='rtabmap_odom',
            executable='icp_odometry',
            output='screen',
            parameters=[{
                'frame_id': LaunchConfiguration('base_frame_id'),
                'odom_frame_id': LaunchConfiguration('odom_frame_id'),
                'wait_for_transform': 0.3,
                'expected_update_rate': LaunchConfiguration('icp_expected_update_rate'),
                'max_update_rate': LaunchConfiguration('icp_max_update_rate'),
                'topic_queue_size': 1,
                'qos': 1,
                'subscribe_odom_info': False,
                'deskewing': LaunchConfiguration('deskewing'),
                'use_sim_time': LaunchConfiguration('use_sim_time'),
            }],
            remappings=[
                ('scan', '/unused_scan_for_hesai_mapping'),
                ('scan_cloud', LaunchConfiguration('rtabmap_scan_cloud_topic'))
            ],
            arguments=[
                'Icp/PointToPlane', 'true',
                'Icp/Iterations', '10',
                'Icp/VoxelSize', LaunchConfiguration('rtabmap_voxel_size'),
                'Icp/Epsilon', '0.001',
                'Icp/PointToPlaneK', '20',
                'Icp/PointToPlaneRadius', '0',
                'Icp/PointToPlaneMinComplexity', LaunchConfiguration('icp_point_to_plane_min_complexity'),
                'Icp/PointToPlaneLowComplexityStrategy', '1',
                'Icp/MaxTranslation', LaunchConfiguration('icp_max_translation'),
                'Icp/MaxRotation', LaunchConfiguration('icp_max_rotation'),
                'Icp/MaxCorrespondenceDistance', LaunchConfiguration('icp_max_correspondence_distance'),
                'Icp/Strategy', '1',
                'Icp/OutlierRatio', LaunchConfiguration('icp_outlier_ratio'),
                'Icp/CorrespondenceRatio', LaunchConfiguration('icp_correspondence_ratio'),
                'Icp/Force4DoF', LaunchConfiguration('icp_force_4dof'),
                'Icp/RangeMax', LaunchConfiguration('icp_range_max'),
                'Odom/AlignWithGround', LaunchConfiguration('odom_align_with_ground'),
                'Odom/FilteringStrategy', LaunchConfiguration('odom_filtering_strategy'),
                'Odom/GuessMotion', 'true',
                'Odom/GuessSmoothingDelay', LaunchConfiguration('odom_guess_smoothing_delay'),
                'Odom/Holonomic', LaunchConfiguration('odom_holonomic'),
                'Odom/ScanKeyFrameThr', LaunchConfiguration('odom_scan_keyframe_thr'),
                'OdomF2M/ScanSubtractRadius', LaunchConfiguration('odom_scan_subtract_radius'),
                'OdomF2M/ScanMaxSize', LaunchConfiguration('odom_scan_max_size'),
                'OdomF2M/BundleAdjustment', 'false',
                '--ros-args',
                '--log-level',
                LaunchConfiguration('icp_odometry_log_level'),
            ],
            condition=IfCondition(PythonExpression([
                '"', LaunchConfiguration('odom_source'), '" == "icp"'
            ]))
        ),

        # ============ point_cloud_assembler Node ============
        Node(
            package='rtabmap_util',
            executable='point_cloud_assembler',
            output='screen',
            parameters=[{
                'max_clouds': 10,
                'fixed_frame_id': '',
                'use_sim_time': LaunchConfiguration('use_sim_time'),
            }],
            remappings=[
                ('cloud', 'odom_filtered_input_scan')
            ],
            condition=IfCondition(LaunchConfiguration('use_cloud_assembler'))
        ),

        # ============ RTAB-Map Node (Reusing DB) ============
        Node(
            package='rtabmap_slam',
            executable='rtabmap',
            name='rtabmap',
            output='screen',
            parameters=[{
                'frame_id': LaunchConfiguration('rtabmap_frame_id'),
                'subscribe_depth': False,
                'subscribe_rgb': False,
                'subscribe_scan_cloud': True,
                'approx_sync': True,
                'topic_queue_size': 30,
                'sync_queue_size': 30,
                'qos': 1,
                'qos_odom': 1,
                'wait_for_transform': 0.3,
                'use_sim_time': LaunchConfiguration('use_sim_time'),
            }],
            remappings=[
                ('odom', LaunchConfiguration('odom_topic')),
                ('scan_cloud', LaunchConfiguration('rtabmap_scan_cloud_topic'))
            ],
            # Only launch if restart_map == "false"
            condition=IfCondition(
                PythonExpression([
                    '"', LaunchConfiguration('restart_map'), '" == "false"'
                ])
            ),
            arguments=[
                # Decide if we do mapping (IncrementalMemory=true) or localization (false)
                'Mem/IncrementalMemory',
                PythonExpression([
                    '"false" if "', LaunchConfiguration('localize_only'), '" == "true" else "true"'
                ]),

                # If localizing only, we often want to load all nodes in WM:
                'Mem/InitWMWithAllNodes',
                PythonExpression([
                    '"true" if "', LaunchConfiguration('localize_only'), '" == "true" else "false"'
                ]),

                # Optionally do not grow DB in localization mode:
                'Mem/LocalizationDataSaved',
                PythonExpression([
                    '"false" if "', LaunchConfiguration('localize_only'), '" == "true" else "true"'
                ]),

                # Other parameters unchanged...
                'RGBD/ProximityMaxGraphDepth', '0',
                'RGBD/ProximityBySpace', LaunchConfiguration('enable_loop_closure'),
                'RGBD/ProximityPathMaxNeighbors',
                PythonExpression([
                    '"1" if "', LaunchConfiguration('enable_loop_closure'), '" == "true" else "0"'
                ]),
                'RGBD/AggressiveLoopThr',
                PythonExpression([
                    '"0.05" if "', LaunchConfiguration('enable_loop_closure'), '" == "true" else "1"'
                ]),
                'RGBD/OptimizeFromGraphEnd', LaunchConfiguration('rtabmap_optimize_from_graph_end'),
                'RGBD/OptimizeMaxError', LaunchConfiguration('rtabmap_optimize_max_error'),
                'RGBD/AngularUpdate', LaunchConfiguration('rtabmap_angular_update'),
                'RGBD/LinearUpdate', LaunchConfiguration('rtabmap_linear_update'),
                'RGBD/CreateOccupancyGrid', 'true',
                'Grid/Sensor', '0',
                'Grid/3D', 'true',
                'Grid/NormalsSegmentation', 'true',
                'Grid/GroundIsObstacle', 'false',
                'Grid/FlatObstacleDetected', LaunchConfiguration('grid_flat_obstacles'),
                'Grid/MaxObstacleHeight', LaunchConfiguration('grid_max_obstacle_height'),
                'Grid/MinClusterSize', LaunchConfiguration('grid_min_cluster_size'),
                'Grid/RangeMax', LaunchConfiguration('grid_range_max'),
                'Grid/NoiseFilteringRadius', LaunchConfiguration('grid_noise_filtering_radius'),
                'Grid/NoiseFilteringMinNeighbors', LaunchConfiguration('grid_noise_filtering_min_neighbors'),
                'Grid/PreVoxelFiltering', 'true',
                'Mem/NotLinkedNodesKept', 'false',
                'Mem/STMSize', '30',
                'Mem/LaserScanNormalK', '20',
                'Reg/Strategy', '1',
                'Icp/VoxelSize', LaunchConfiguration('rtabmap_voxel_size'),
                'Icp/PointToPlaneK', '20',
                'Icp/PointToPlaneRadius', '0',
                'Icp/PointToPlane', 'true',
                'Icp/Iterations', '10',
                'Icp/Epsilon', '0.001',
                'Icp/PointToPlaneMinComplexity', LaunchConfiguration('icp_point_to_plane_min_complexity'),
                'Icp/PointToPlaneLowComplexityStrategy', '1',
                'Icp/MaxTranslation', LaunchConfiguration('icp_max_translation'),
                'Icp/MaxRotation', LaunchConfiguration('icp_max_rotation'),
                'Icp/MaxCorrespondenceDistance', LaunchConfiguration('icp_max_correspondence_distance'),
                'Icp/Strategy', '1',
                'Icp/OutlierRatio', LaunchConfiguration('icp_outlier_ratio'),
                'Icp/CorrespondenceRatio', '0.2',
                'Icp/Force4DoF', LaunchConfiguration('icp_force_4dof'),
                'Icp/RangeMax', LaunchConfiguration('icp_range_max'),

                '--ros-args',
                '--log-level',
                LaunchConfiguration('rtabmap_log_level'),
            ]
        ),

        # ============ RTAB-Map Node (Restarting DB) ============
        Node(
            package='rtabmap_slam',
            executable='rtabmap',
            name='rtabmap_reset',
            output='screen',
            parameters=[{
                'frame_id': LaunchConfiguration('rtabmap_frame_id'),
                'subscribe_depth': False,
                'subscribe_rgb': False,
                'subscribe_scan_cloud': True,
                'approx_sync': True,
                'topic_queue_size': 30,
                'sync_queue_size': 30,
                'qos': 1,
                'qos_odom': 1,
                'wait_for_transform': 0.3,
                'use_sim_time': LaunchConfiguration('use_sim_time'),
            }],
            remappings=[
                ('odom', LaunchConfiguration('odom_topic')),
                ('scan_cloud', LaunchConfiguration('rtabmap_scan_cloud_topic'))
            ],
            # Only launch if restart_map == "true"
            condition=IfCondition(
                PythonExpression([
                    '"', LaunchConfiguration('restart_map'), '" == "true"'
                ])
            ),
            arguments=[
                # Same logic for mapping vs. localization:
                'Mem/IncrementalMemory',
                PythonExpression([
                    '"false" if "', LaunchConfiguration('localize_only'), '" == "true" else "true"'
                ]),
                'Mem/InitWMWithAllNodes',
                PythonExpression([
                    '"true" if "', LaunchConfiguration('localize_only'), '" == "true" else "false"'
                ]),
                'Mem/LocalizationDataSaved',
                PythonExpression([
                    '"false" if "', LaunchConfiguration('localize_only'), '" == "true" else "true"'
                ]),

                # Wipe old DB:
                '--delete_db_on_start',

                # Other parameters unchanged...
                'RGBD/ProximityMaxGraphDepth', '0',
                'RGBD/ProximityBySpace', LaunchConfiguration('enable_loop_closure'),
                'RGBD/ProximityPathMaxNeighbors',
                PythonExpression([
                    '"1" if "', LaunchConfiguration('enable_loop_closure'), '" == "true" else "0"'
                ]),
                'RGBD/AggressiveLoopThr',
                PythonExpression([
                    '"0.05" if "', LaunchConfiguration('enable_loop_closure'), '" == "true" else "1"'
                ]),
                'RGBD/OptimizeFromGraphEnd', LaunchConfiguration('rtabmap_optimize_from_graph_end'),
                'RGBD/OptimizeMaxError', LaunchConfiguration('rtabmap_optimize_max_error'),
                'RGBD/AngularUpdate', LaunchConfiguration('rtabmap_angular_update'),
                'RGBD/LinearUpdate', LaunchConfiguration('rtabmap_linear_update'),
                'RGBD/CreateOccupancyGrid', 'true',
                'Grid/Sensor', '0',
                'Grid/3D', 'true',
                'Grid/NormalsSegmentation', 'true',
                'Grid/GroundIsObstacle', 'false',
                'Grid/FlatObstacleDetected', LaunchConfiguration('grid_flat_obstacles'),
                'Grid/MaxObstacleHeight', LaunchConfiguration('grid_max_obstacle_height'),
                'Grid/MinClusterSize', LaunchConfiguration('grid_min_cluster_size'),
                'Grid/RangeMax', LaunchConfiguration('grid_range_max'),
                'Grid/NoiseFilteringRadius', LaunchConfiguration('grid_noise_filtering_radius'),
                'Grid/NoiseFilteringMinNeighbors', LaunchConfiguration('grid_noise_filtering_min_neighbors'),
                'Grid/PreVoxelFiltering', 'true',
                'Mem/NotLinkedNodesKept', 'false',
                'Mem/STMSize', '30',
                'Mem/LaserScanNormalK', '20',
                'Reg/Strategy', '1',
                'Icp/VoxelSize', LaunchConfiguration('rtabmap_voxel_size'),
                'Icp/PointToPlaneK', '20',
                'Icp/PointToPlaneRadius', '0',
                'Icp/PointToPlane', 'true',
                'Icp/Iterations', '10',
                'Icp/Epsilon', '0.001',
                'Icp/PointToPlaneMinComplexity', LaunchConfiguration('icp_point_to_plane_min_complexity'),
                'Icp/PointToPlaneLowComplexityStrategy', '1',
                'Icp/MaxTranslation', LaunchConfiguration('icp_max_translation'),
                'Icp/MaxRotation', LaunchConfiguration('icp_max_rotation'),
                'Icp/MaxCorrespondenceDistance', LaunchConfiguration('icp_max_correspondence_distance'),
                'Icp/Strategy', '1',
                'Icp/OutlierRatio', LaunchConfiguration('icp_outlier_ratio'),
                'Icp/CorrespondenceRatio', '0.2',
                'Icp/Force4DoF', LaunchConfiguration('icp_force_4dof'),
                'Icp/RangeMax', LaunchConfiguration('icp_range_max'),

                '--ros-args',
                '--log-level',
                LaunchConfiguration('rtabmap_log_level'),
            ]
        ),

        # ============ (Optional) RTAB-Map Viz Node ============
        Node(
            package='rtabmap_viz',
            executable='rtabmap_viz',
            output='screen',
            parameters=[{
                'frame_id': LaunchConfiguration('rtabmap_frame_id'),
                'odom_frame_id': LaunchConfiguration('odom_frame_id'),
                'subscribe_odom_info': True,
                'subscribe_scan_cloud': True,
                'approx_sync': True,
                'use_sim_time': LaunchConfiguration('use_sim_time'),
            }],
            remappings=[
                ('odom', LaunchConfiguration('odom_topic')),
                ('scan_cloud', LaunchConfiguration('rtabmap_scan_cloud_topic'))
            ],
            condition=IfCondition(LaunchConfiguration('use_rtabmapviz'))
        ),

        # ============ Static TF between base_link and RTAB-Map robot frame ============
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            arguments=[
                '--x', LaunchConfiguration('rtabmap_frame_x'),
                '--y', LaunchConfiguration('rtabmap_frame_y'),
                '--z', LaunchConfiguration('rtabmap_frame_z'),
                '--roll', LaunchConfiguration('rtabmap_frame_roll'),
                '--pitch', LaunchConfiguration('rtabmap_frame_pitch'),
                '--yaw', LaunchConfiguration('rtabmap_frame_yaw'),
                '--frame-id', LaunchConfiguration('base_frame_id'),
                '--child-frame-id', LaunchConfiguration('rtabmap_frame_id'),
            ],
            condition=IfCondition(LaunchConfiguration('publish_static_tf'))
        ),

        # ============ Static TF between base_link and Hesai LiDAR frame ============
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            arguments=[
                '--x', LaunchConfiguration('lidar_tf_x'),
                '--y', LaunchConfiguration('lidar_tf_y'),
                '--z', LaunchConfiguration('lidar_tf_z'),
                '--roll', LaunchConfiguration('lidar_tf_roll'),
                '--pitch', LaunchConfiguration('lidar_tf_pitch'),
                '--yaw', LaunchConfiguration('lidar_tf_yaw'),
                '--frame-id', LaunchConfiguration('base_frame_id'),
                '--child-frame-id', LaunchConfiguration('lidar_frame_id'),
            ],
            condition=IfCondition(LaunchConfiguration('publish_lidar_tf'))
        ),
    ])
