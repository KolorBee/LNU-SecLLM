from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.conditions import IfCondition
from launch_ros.substitutions import FindPackageShare
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    return LaunchDescription([

        DeclareLaunchArgument(
            name='use_rviz',
            default_value='true',
            choices=['true','false'],
            description='Open RVIZ with the go2_slam_nav display config'
        ),

        DeclareLaunchArgument(
            name='use_nav2_rviz',
            default_value='false',
            choices=['true','false'],
            description='Open the default Nav2 RVIZ config in a second RVIZ window'
        ),
        DeclareLaunchArgument(
            name='use_sim_time',
            default_value='false',
            choices=['true','false'],
            description='Use simulation clock if true'
        ),

        DeclareLaunchArgument(
            name='localize_only',
            default_value='true',
            choices=['true','false'],
            description='Localize only, do not change loaded map'
        ),

        DeclareLaunchArgument(
            name='restart_map',
            default_value='false',
            choices=['true','false'],
            description='Delete previous map and restart'
        ),
        
        DeclareLaunchArgument(
            name='log_level',
            default_value='warn',
            choices=['debug', 'info', 'warn', 'error', 'fatal'],
            description='Logging level for sport_ctrl node'
        ),
        DeclareLaunchArgument(
            name='publish_go2_marker',
            default_value='true',
            choices=['true','false'],
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
            choices=['true','false'],
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
        DeclareLaunchArgument(name='lidar_tf_x', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_y', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_z', default_value='0.10'),
        DeclareLaunchArgument(name='lidar_tf_roll', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_pitch', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_yaw', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_topic', default_value='/lidar_points'),
        DeclareLaunchArgument(name='icp_lidar_topic', default_value='/lidar_points_slam'),
        DeclareLaunchArgument(name='use_lidar_throttle', default_value='true'),
        DeclareLaunchArgument(name='lidar_throttle_rate', default_value='4.0'),
        DeclareLaunchArgument(name='lidar_point_stride', default_value='2'),
        DeclareLaunchArgument(name='lidar_throttle_stamp_mode', default_value='now'),
        DeclareLaunchArgument(name='publish_viz_clouds', default_value='false'),
        DeclareLaunchArgument(name='cloud_map_viz_topic', default_value='/cloud_map_viz'),
        DeclareLaunchArgument(name='cloud_map_viz_throttle_rate', default_value='0.2'),
        DeclareLaunchArgument(name='cloud_map_viz_point_stride', default_value='16'),
        DeclareLaunchArgument(name='publish_visual_3d_map', default_value='true'),
        DeclareLaunchArgument(name='visual_3d_map_topic', default_value='/visual_cloud_map'),
        DeclareLaunchArgument(name='visual_3d_map_rate', default_value='0.5'),
        DeclareLaunchArgument(name='visual_3d_map_input_rate', default_value='1.0'),
        DeclareLaunchArgument(name='visual_3d_map_point_stride', default_value='4'),
        DeclareLaunchArgument(name='visual_3d_map_voxel_size', default_value='0.08'),
        DeclareLaunchArgument(name='visual_3d_map_max_points', default_value='150000'),
        DeclareLaunchArgument(name='visual_3d_map_min_z', default_value='-0.40'),
        DeclareLaunchArgument(name='visual_3d_map_max_z', default_value='2.20'),
        DeclareLaunchArgument(name='visual_3d_map_min_range', default_value='0.20'),
        DeclareLaunchArgument(name='visual_3d_map_max_range', default_value='8.0'),
        DeclareLaunchArgument(name='slam_filter_enabled', default_value='true'),
        DeclareLaunchArgument(name='slam_filter_min_z', default_value='-0.35'),
        DeclareLaunchArgument(name='slam_filter_max_z', default_value='1.80'),
        DeclareLaunchArgument(name='slam_filter_min_range', default_value='0.20'),
        DeclareLaunchArgument(name='slam_filter_max_range', default_value='10.0'),
        DeclareLaunchArgument(name='slam_self_filter_enabled', default_value='true'),
        DeclareLaunchArgument(name='slam_self_min_x', default_value='-0.65'),
        DeclareLaunchArgument(name='slam_self_max_x', default_value='0.60'),
        DeclareLaunchArgument(name='slam_self_min_y', default_value='-0.45'),
        DeclareLaunchArgument(name='slam_self_max_y', default_value='0.45'),
        DeclareLaunchArgument(name='slam_self_min_z', default_value='-0.50'),
        DeclareLaunchArgument(name='slam_self_max_z', default_value='0.80'),
        DeclareLaunchArgument(name='use_nav_obstacle_filter', default_value='true'),
        DeclareLaunchArgument(name='nav_obstacle_topic', default_value='/lidar_points_nav'),
        DeclareLaunchArgument(name='nav_obstacle_rate', default_value='5.0'),
        DeclareLaunchArgument(name='nav_obstacle_point_stride', default_value='2'),
        DeclareLaunchArgument(name='nav_obstacle_min_z', default_value='-0.25'),
        DeclareLaunchArgument(name='nav_obstacle_max_z', default_value='1.35'),
        DeclareLaunchArgument(name='nav_obstacle_min_range', default_value='0.20'),
        DeclareLaunchArgument(name='nav_obstacle_max_range', default_value='4.0'),
        DeclareLaunchArgument(name='odom_source', default_value='unitree'),
        DeclareLaunchArgument(name='unitree_odom_topic', default_value='/utlidar/robot_odom'),
        DeclareLaunchArgument(name='odom_topic', default_value='/odom'),
        DeclareLaunchArgument(name='ekf_odom_topic', default_value='/odom_unitree'),
        DeclareLaunchArgument(name='unitree_imu_topic', default_value='/utlidar/imu'),
        DeclareLaunchArgument(name='publish_unitree_imu_tf', default_value='true'),
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
        ),
        DeclareLaunchArgument(name='publish_odom_tf', default_value='true'),
        DeclareLaunchArgument(name='odom_relay_rate', default_value='30.0'),
        DeclareLaunchArgument(name='odom_stamp_mode', default_value='now'),
        DeclareLaunchArgument(name='odom_flatten_to_2d', default_value='true'),
        DeclareLaunchArgument(name='odom_replace_zero_covariance', default_value='false'),
        DeclareLaunchArgument(name='odom_align_with_ground', default_value='false'),
        DeclareLaunchArgument(name='icp_range_max', default_value='12.0'),
        DeclareLaunchArgument(name='rtabmap_voxel_size', default_value='0.12'),
        DeclareLaunchArgument(name='icp_expected_update_rate', default_value='10.0'),
        DeclareLaunchArgument(name='icp_max_update_rate', default_value='6.0'),
        DeclareLaunchArgument(name='icp_max_translation', default_value='0.45'),
        DeclareLaunchArgument(name='icp_max_rotation', default_value='0.78'),
        DeclareLaunchArgument(name='icp_max_correspondence_distance', default_value='0.35'),
        DeclareLaunchArgument(name='icp_correspondence_ratio', default_value='0.08'),
        DeclareLaunchArgument(name='icp_outlier_ratio', default_value='0.65'),
        DeclareLaunchArgument(name='icp_force_4dof', default_value='true'),
        DeclareLaunchArgument(name='icp_point_to_plane_min_complexity', default_value='0.02'),
        DeclareLaunchArgument(name='odom_filtering_strategy', default_value='1'),
        DeclareLaunchArgument(name='odom_guess_smoothing_delay', default_value='0.0'),
        DeclareLaunchArgument(name='odom_holonomic', default_value='true'),
        DeclareLaunchArgument(name='enable_loop_closure', default_value='false'),
        DeclareLaunchArgument(name='rtabmap_optimize_from_graph_end', default_value='true'),
        DeclareLaunchArgument(name='rtabmap_optimize_max_error', default_value='2.0'),
        DeclareLaunchArgument(name='grid_range_max', default_value='6.0'),
        DeclareLaunchArgument(name='grid_max_obstacle_height', default_value='1.2'),
        DeclareLaunchArgument(name='grid_min_cluster_size', default_value='20'),
        DeclareLaunchArgument(name='grid_flat_obstacles', default_value='false'),
        DeclareLaunchArgument(name='grid_noise_filtering_radius', default_value='0.20'),
        DeclareLaunchArgument(name='grid_noise_filtering_min_neighbors', default_value='8'),

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
            package='go2_cmd_processor',
            executable='sport_ctrl',
            name='sport_ctrl',
            output='screen',
            parameters=[{
                'log_level': LaunchConfiguration('log_level')
            }]
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_cloud_throttle',
            name='go2_nav_cloud_filter',
            output='screen',
            parameters=[{
                'input_topic': LaunchConfiguration('lidar_topic'),
                'output_topic': LaunchConfiguration('nav_obstacle_topic'),
                'max_rate': LaunchConfiguration('nav_obstacle_rate'),
                'stamp_mode': 'now',
                'point_stride': LaunchConfiguration('nav_obstacle_point_stride'),
                'filter_enabled': True,
                'min_z': LaunchConfiguration('nav_obstacle_min_z'),
                'max_z': LaunchConfiguration('nav_obstacle_max_z'),
                'min_range': LaunchConfiguration('nav_obstacle_min_range'),
                'max_range': LaunchConfiguration('nav_obstacle_max_range'),
                'self_filter_enabled': True,
                'self_min_x': -0.65,
                'self_max_x': 0.60,
                'self_min_y': -0.45,
                'self_max_y': 0.45,
                'self_min_z': -0.50,
                'self_max_z': 0.80,
            }],
            condition=IfCondition(LaunchConfiguration('use_nav_obstacle_filter')),
        ),
        
      #  IncludeLaunchDescription(
       #     PythonLaunchDescriptionSource(
        #        PathJoinSubstitution([
         #           FindPackageShare('rtabmap_launch_pkg'),
          #          'launch',
           #         'control.launch.py'
            #    ])
            #),
            #launch_arguments=[
            #    ('use_rviz', 'false'),
            #],
        #),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('go2_slam_nav'),
                    'launch',
                    'mapping.launch.py'
                ])
            ),
            launch_arguments=[
                ('use_rviz', 'false'),
                ('use_rtabmapviz', 'false'),
                ('use_sim_time', LaunchConfiguration('use_sim_time')),
                ('publish_static_tf', 'false'),
                ('publish_lidar_tf', 'true'),
                ('lidar_topic', LaunchConfiguration('lidar_topic')),
                ('icp_lidar_topic', LaunchConfiguration('icp_lidar_topic')),
                ('use_lidar_throttle', LaunchConfiguration('use_lidar_throttle')),
                ('lidar_throttle_rate', LaunchConfiguration('lidar_throttle_rate')),
                ('lidar_point_stride', LaunchConfiguration('lidar_point_stride')),
                ('lidar_throttle_stamp_mode', LaunchConfiguration('lidar_throttle_stamp_mode')),
                ('publish_viz_clouds', LaunchConfiguration('publish_viz_clouds')),
                ('cloud_map_viz_topic', LaunchConfiguration('cloud_map_viz_topic')),
                ('cloud_map_viz_throttle_rate', LaunchConfiguration('cloud_map_viz_throttle_rate')),
                ('cloud_map_viz_point_stride', LaunchConfiguration('cloud_map_viz_point_stride')),
                ('publish_visual_3d_map', LaunchConfiguration('publish_visual_3d_map')),
                ('visual_3d_map_topic', LaunchConfiguration('visual_3d_map_topic')),
                ('visual_3d_map_rate', LaunchConfiguration('visual_3d_map_rate')),
                ('visual_3d_map_input_rate', LaunchConfiguration('visual_3d_map_input_rate')),
                ('visual_3d_map_point_stride', LaunchConfiguration('visual_3d_map_point_stride')),
                ('visual_3d_map_voxel_size', LaunchConfiguration('visual_3d_map_voxel_size')),
                ('visual_3d_map_max_points', LaunchConfiguration('visual_3d_map_max_points')),
                ('visual_3d_map_min_z', LaunchConfiguration('visual_3d_map_min_z')),
                ('visual_3d_map_max_z', LaunchConfiguration('visual_3d_map_max_z')),
                ('visual_3d_map_min_range', LaunchConfiguration('visual_3d_map_min_range')),
                ('visual_3d_map_max_range', LaunchConfiguration('visual_3d_map_max_range')),
                ('slam_filter_enabled', LaunchConfiguration('slam_filter_enabled')),
                ('slam_filter_min_z', LaunchConfiguration('slam_filter_min_z')),
                ('slam_filter_max_z', LaunchConfiguration('slam_filter_max_z')),
                ('slam_filter_min_range', LaunchConfiguration('slam_filter_min_range')),
                ('slam_filter_max_range', LaunchConfiguration('slam_filter_max_range')),
                ('slam_self_filter_enabled', LaunchConfiguration('slam_self_filter_enabled')),
                ('slam_self_min_x', LaunchConfiguration('slam_self_min_x')),
                ('slam_self_max_x', LaunchConfiguration('slam_self_max_x')),
                ('slam_self_min_y', LaunchConfiguration('slam_self_min_y')),
                ('slam_self_max_y', LaunchConfiguration('slam_self_max_y')),
                ('slam_self_min_z', LaunchConfiguration('slam_self_min_z')),
                ('slam_self_max_z', LaunchConfiguration('slam_self_max_z')),
                ('lidar_frame_id', 'hesai_lidar'),
                ('odom_source', LaunchConfiguration('odom_source')),
                ('unitree_odom_topic', LaunchConfiguration('unitree_odom_topic')),
                ('odom_topic', LaunchConfiguration('odom_topic')),
                ('ekf_odom_topic', LaunchConfiguration('ekf_odom_topic')),
                ('unitree_imu_topic', LaunchConfiguration('unitree_imu_topic')),
                ('publish_unitree_imu_tf', LaunchConfiguration('publish_unitree_imu_tf')),
                ('unitree_imu_tf_x', LaunchConfiguration('unitree_imu_tf_x')),
                ('unitree_imu_tf_y', LaunchConfiguration('unitree_imu_tf_y')),
                ('unitree_imu_tf_z', LaunchConfiguration('unitree_imu_tf_z')),
                ('unitree_imu_tf_roll', LaunchConfiguration('unitree_imu_tf_roll')),
                ('unitree_imu_tf_pitch', LaunchConfiguration('unitree_imu_tf_pitch')),
                ('unitree_imu_tf_yaw', LaunchConfiguration('unitree_imu_tf_yaw')),
                ('ekf_config_path', LaunchConfiguration('ekf_config_path')),
                ('publish_odom_tf', LaunchConfiguration('publish_odom_tf')),
                ('odom_relay_rate', LaunchConfiguration('odom_relay_rate')),
                ('odom_stamp_mode', LaunchConfiguration('odom_stamp_mode')),
                ('odom_flatten_to_2d', LaunchConfiguration('odom_flatten_to_2d')),
                ('odom_replace_zero_covariance', LaunchConfiguration('odom_replace_zero_covariance')),
                ('use_cloud_assembler', 'false'),
                ('rtabmap_scan_cloud_topic', LaunchConfiguration('icp_lidar_topic')),
                ('publish_go2_marker', LaunchConfiguration('publish_go2_marker')),
                ('marker_publish_rate', LaunchConfiguration('marker_publish_rate')),
                ('use_go2_urdf', LaunchConfiguration('use_go2_urdf')),
                ('go2_urdf_path', LaunchConfiguration('go2_urdf_path')),
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
                ('enable_loop_closure', LaunchConfiguration('enable_loop_closure')),
                ('rtabmap_optimize_from_graph_end', LaunchConfiguration('rtabmap_optimize_from_graph_end')),
                ('rtabmap_optimize_max_error', LaunchConfiguration('rtabmap_optimize_max_error')),
                ('grid_range_max', LaunchConfiguration('grid_range_max')),
                ('grid_max_obstacle_height', LaunchConfiguration('grid_max_obstacle_height')),
                ('grid_min_cluster_size', LaunchConfiguration('grid_min_cluster_size')),
                ('grid_flat_obstacles', LaunchConfiguration('grid_flat_obstacles')),
                ('grid_noise_filtering_radius', LaunchConfiguration('grid_noise_filtering_radius')),
                ('grid_noise_filtering_min_neighbors', LaunchConfiguration('grid_noise_filtering_min_neighbors')),
                ('localize_only', LaunchConfiguration('localize_only')),
                ('restart_map', LaunchConfiguration('restart_map')),
            ],
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('nav2_bringup'),
                    'launch',
                    'navigation_launch.py'
                ])
            ),
            launch_arguments=[
                ('params_file',
                    PathJoinSubstitution([
                        FindPackageShare('go2_slam_nav'),
                        'config',
                        'nav2_params.yaml'
                    ])
                ),
                ('use_sim_time', LaunchConfiguration('use_sim_time')),
                ('autostart', 'true'),
            ],
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('nav2_bringup'),
                    'launch',
                    'rviz_launch.py'
                ])
            ),
            condition=IfCondition(LaunchConfiguration('use_nav2_rviz')),
        ),
    ])
