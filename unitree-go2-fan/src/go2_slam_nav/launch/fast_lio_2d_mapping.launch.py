from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            name='use_rviz',
            default_value='true',
            choices=['true', 'false'],
            description='Open RViz with FAST-LIO, 3D map, and projected 2D map displays'
        ),
        DeclareLaunchArgument(
            name='use_sim_time',
            default_value='false',
            choices=['true', 'false'],
            description='Use simulation clock if true'
        ),
        DeclareLaunchArgument(
            name='start_lidar_driver',
            default_value='true',
            choices=['true', 'false'],
            description='Start the Hesai JT128 driver'
        ),
        DeclareLaunchArgument(
            name='publish_map_to_lio_tf',
            default_value='true',
            choices=['true', 'false'],
            description='Publish an identity map -> lio_map TF for Nav2-compatible map frame'
        ),
        DeclareLaunchArgument(
            name='restart_map',
            default_value='true',
            choices=['true', 'false'],
            description='Start with a fresh in-memory FAST-LIO 3D/2D map when true'
        ),
        DeclareLaunchArgument(name='lidar_topic', default_value='/lidar_points'),
        DeclareLaunchArgument(name='lio_cloud_map_topic', default_value='/lio_cloud_map'),
        DeclareLaunchArgument(name='lio_cloud_map_input_rate', default_value='1.0'),
        DeclareLaunchArgument(name='lio_cloud_map_publish_rate', default_value='0.5'),
        DeclareLaunchArgument(name='lio_cloud_map_voxel_size', default_value='0.10'),
        DeclareLaunchArgument(name='lio_cloud_map_max_points', default_value='250000'),
        DeclareLaunchArgument(name='lio_cloud_map_save_format', default_value='pcd'),
        DeclareLaunchArgument(name='save_lio_cloud_map_on_shutdown', default_value='true'),
        DeclareLaunchArgument(name='lidar_tf_x', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_y', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_z', default_value='0.10'),
        DeclareLaunchArgument(name='lidar_tf_roll', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_pitch', default_value='0.0'),
        DeclareLaunchArgument(
            name='lidar_tf_yaw',
            default_value='-0.22689280275926285',
            description='Hesai JT128 yaw relative to base_link, radians'
        ),
        DeclareLaunchArgument(
            name='publish_static_joint_states',
            default_value='true',
            choices=['true', 'false'],
            description='Publish neutral standing joint states for RViz'
        ),
        DeclareLaunchArgument(
            name='publish_lowstate_joint_states',
            default_value='true',
            choices=['true', 'false'],
            description='Relay LowState to /joint_states when static joints are disabled'
        ),
        DeclareLaunchArgument(name='lowstate_topic', default_value='/lowstate'),
        DeclareLaunchArgument(name='joint_states_topic', default_value='/joint_states'),
        DeclareLaunchArgument(name='grid_input_topic', default_value='/lio_cloud_map'),
        DeclareLaunchArgument(name='map_topic', default_value='/map'),
        DeclareLaunchArgument(name='map_frame_id', default_value='map'),
        DeclareLaunchArgument(name='grid_resolution', default_value='0.05'),
        DeclareLaunchArgument(name='grid_publish_rate', default_value='1.0'),
        DeclareLaunchArgument(name='grid_map_padding', default_value='1.0'),
        DeclareLaunchArgument(
            name='grid_stable_bounds',
            default_value='true',
            choices=['true', 'false'],
            description='Keep the 2D map canvas stable and expand it only when needed'
        ),
        DeclareLaunchArgument(
            name='grid_growth_margin',
            default_value='2.0',
            description='Extra meters reserved around new projected map bounds'
        ),
        DeclareLaunchArgument(
            name='grid_bounds_snap',
            default_value='1.0',
            description='Snap stable map bounds to this meter interval'
        ),
        DeclareLaunchArgument(
            name='grid_unknown_as_free',
            default_value='true',
            choices=['true', 'false'],
            description='Fill projected map background as free for initial Nav2 testing'
        ),
        DeclareLaunchArgument(name='grid_obstacle_min_z', default_value='0.18'),
        DeclareLaunchArgument(name='grid_obstacle_max_z', default_value='1.60'),
        DeclareLaunchArgument(name='grid_min_obstacle_points', default_value='1'),
        DeclareLaunchArgument(name='grid_obstacle_dilation_radius', default_value='0.05'),
        DeclareLaunchArgument(name='grid_clear_robot_radius', default_value='0.45'),
        DeclareLaunchArgument(name='grid_max_cells', default_value='4000000'),
        DeclareLaunchArgument(name='grid_save_service', default_value='/save_lio_2d_map'),
        DeclareLaunchArgument(
            name='grid_save_dir',
            default_value='/home/star/go2_maps/fast_lio2'
        ),
        DeclareLaunchArgument(name='grid_map_name', default_value='go2_lio_2d_map'),
        DeclareLaunchArgument(
            name='save_lio_2d_map_on_shutdown',
            default_value='true',
            choices=['true', 'false'],
            description='Save the projected 2D map when launch is stopped'
        ),

        GroupAction(
            scoped=True,
            actions=[
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(
                        PathJoinSubstitution([
                            FindPackageShare('go2_slam_nav'),
                            'launch',
                            'fast_lio2.launch.py'
                        ])
                    ),
                    launch_arguments=[
                        ('use_rviz', 'false'),
                        ('use_sim_time', LaunchConfiguration('use_sim_time')),
                        ('start_lidar_driver', LaunchConfiguration('start_lidar_driver')),
                        ('lidar_topic', LaunchConfiguration('lidar_topic')),
                        ('lidar_tf_x', LaunchConfiguration('lidar_tf_x')),
                        ('lidar_tf_y', LaunchConfiguration('lidar_tf_y')),
                        ('lidar_tf_z', LaunchConfiguration('lidar_tf_z')),
                        ('lidar_tf_roll', LaunchConfiguration('lidar_tf_roll')),
                        ('lidar_tf_pitch', LaunchConfiguration('lidar_tf_pitch')),
                        ('lidar_tf_yaw', LaunchConfiguration('lidar_tf_yaw')),
                        ('publish_lio_cloud_map', 'true'),
                        ('lio_cloud_map_topic', LaunchConfiguration('lio_cloud_map_topic')),
                        ('lio_cloud_map_input_rate',
                            LaunchConfiguration('lio_cloud_map_input_rate')),
                        ('lio_cloud_map_publish_rate',
                            LaunchConfiguration('lio_cloud_map_publish_rate')),
                        ('lio_cloud_map_voxel_size',
                            LaunchConfiguration('lio_cloud_map_voxel_size')),
                        ('lio_cloud_map_max_points',
                            LaunchConfiguration('lio_cloud_map_max_points')),
                        ('lio_cloud_map_save_format',
                            LaunchConfiguration('lio_cloud_map_save_format')),
                        ('lio_cloud_map_clear_on_start',
                            LaunchConfiguration('restart_map')),
                        ('save_lio_cloud_map_on_shutdown',
                            LaunchConfiguration('save_lio_cloud_map_on_shutdown')),
                        ('publish_static_joint_states',
                            LaunchConfiguration('publish_static_joint_states')),
                        ('publish_lowstate_joint_states',
                            LaunchConfiguration('publish_lowstate_joint_states')),
                        ('lowstate_topic', LaunchConfiguration('lowstate_topic')),
                        ('joint_states_topic', LaunchConfiguration('joint_states_topic')),
                    ],
                ),
            ],
        ),

        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            arguments=[
                '--x', '0.0',
                '--y', '0.0',
                '--z', '0.0',
                '--roll', '0.0',
                '--pitch', '0.0',
                '--yaw', '0.0',
                '--frame-id', 'map',
                '--child-frame-id', 'lio_map',
            ],
            condition=IfCondition(LaunchConfiguration('publish_map_to_lio_tf')),
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_lio_grid_mapper',
            name='go2_lio_grid_mapper',
            output='screen',
            parameters=[{
                'input_topic': LaunchConfiguration('grid_input_topic'),
                'map_topic': LaunchConfiguration('map_topic'),
                'map_frame_id': LaunchConfiguration('map_frame_id'),
                'resolution': LaunchConfiguration('grid_resolution'),
                'publish_rate': LaunchConfiguration('grid_publish_rate'),
                'map_padding': LaunchConfiguration('grid_map_padding'),
                'stable_bounds': LaunchConfiguration('grid_stable_bounds'),
                'growth_margin': LaunchConfiguration('grid_growth_margin'),
                'bounds_snap': LaunchConfiguration('grid_bounds_snap'),
                'unknown_as_free': LaunchConfiguration('grid_unknown_as_free'),
                'obstacle_min_z': LaunchConfiguration('grid_obstacle_min_z'),
                'obstacle_max_z': LaunchConfiguration('grid_obstacle_max_z'),
                'min_obstacle_points': LaunchConfiguration('grid_min_obstacle_points'),
                'obstacle_dilation_radius': LaunchConfiguration(
                    'grid_obstacle_dilation_radius'
                ),
                'clear_robot_radius': LaunchConfiguration('grid_clear_robot_radius'),
                'max_cells': LaunchConfiguration('grid_max_cells'),
                'save_service_name': LaunchConfiguration('grid_save_service'),
                'save_dir': LaunchConfiguration('grid_save_dir'),
                'map_name': LaunchConfiguration('grid_map_name'),
                'save_on_shutdown': LaunchConfiguration('save_lio_2d_map_on_shutdown'),
            }],
        ),

        Node(
            package='rviz2',
            executable='rviz2',
            arguments=[
                '-d',
                PathJoinSubstitution([
                    FindPackageShare('go2_slam_nav'),
                    'config',
                    'lio.rviz'
                ])
            ],
            condition=IfCondition(LaunchConfiguration('use_rviz')),
        ),
    ])
