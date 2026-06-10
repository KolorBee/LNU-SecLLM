from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    TimerAction,
)
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
            description='Open RViz for FAST-LIO + Nav2'
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
            name='start_go2_cmd_bridge',
            default_value='false',
            choices=['true', 'false'],
            description='Publish Nav2 cmd_vel to Unitree sport API. Keep false for dry runs.'
        ),
        DeclareLaunchArgument(
            name='nav2_start_delay',
            default_value='8.0',
            description='Delay Nav2 bring-up so FAST-LIO and Hesai driver initialize first'
        ),
        DeclareLaunchArgument(
            name='nav2_params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('go2_slam_nav'),
                'config',
                'nav2_params_fast_lio.yaml'
            ]),
            description='Nav2 params tuned for FAST-LIO map->base_link TF'
        ),
        DeclareLaunchArgument(name='nav_obstacle_topic', default_value='/lidar_points_nav'),
        DeclareLaunchArgument(name='nav_obstacle_rate', default_value='5.0'),
        DeclareLaunchArgument(name='nav_obstacle_point_stride', default_value='4'),
        DeclareLaunchArgument(name='nav_obstacle_min_z', default_value='0.18'),
        DeclareLaunchArgument(name='nav_obstacle_max_z', default_value='1.60'),
        DeclareLaunchArgument(name='nav_obstacle_min_range', default_value='0.20'),
        DeclareLaunchArgument(name='nav_obstacle_max_range', default_value='4.0'),
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
        DeclareLaunchArgument(name='go2_cmd_vel_topic', default_value='/cmd_vel'),
        DeclareLaunchArgument(name='go2_sport_request_topic', default_value='/api/sport/request'),
        DeclareLaunchArgument(name='go2_cmd_timeout', default_value='0.5'),
        DeclareLaunchArgument(name='go2_cmd_max_vx', default_value='0.15'),
        DeclareLaunchArgument(name='go2_cmd_max_vy', default_value='0.15'),
        DeclareLaunchArgument(name='go2_cmd_max_wz', default_value='0.60'),
        DeclareLaunchArgument(
            name='go2_request_qos_reliability',
            default_value='reliable',
            description='QoS reliability for /api/sport/request: reliable or best_effort'
        ),
        DeclareLaunchArgument(
            name='start_goal_pose_bridge',
            default_value='true',
            choices=['true', 'false'],
            description='Forward RViz /goal_pose messages to Nav2 NavigateToPose action'
        ),
        DeclareLaunchArgument(name='goal_pose_topic', default_value='/goal_pose'),
        DeclareLaunchArgument(name='navigate_action_name', default_value='/navigate_to_pose'),
        DeclareLaunchArgument(
            name='grid_stable_bounds',
            default_value='true',
            choices=['true', 'false'],
            description='Keep the projected 2D map canvas stable for Nav2'
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

        GroupAction(
            scoped=True,
            actions=[
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(
                        PathJoinSubstitution([
                            FindPackageShare('go2_slam_nav'),
                            'launch',
                            'fast_lio_2d_mapping.launch.py'
                        ])
                    ),
                    launch_arguments=[
                        ('use_rviz', 'false'),
                        ('use_sim_time', LaunchConfiguration('use_sim_time')),
                        ('start_lidar_driver', LaunchConfiguration('start_lidar_driver')),
                        ('lidar_tf_x', LaunchConfiguration('lidar_tf_x')),
                        ('lidar_tf_y', LaunchConfiguration('lidar_tf_y')),
                        ('lidar_tf_z', LaunchConfiguration('lidar_tf_z')),
                        ('lidar_tf_roll', LaunchConfiguration('lidar_tf_roll')),
                        ('lidar_tf_pitch', LaunchConfiguration('lidar_tf_pitch')),
                        ('lidar_tf_yaw', LaunchConfiguration('lidar_tf_yaw')),
                        ('grid_stable_bounds', LaunchConfiguration('grid_stable_bounds')),
                        ('grid_growth_margin', LaunchConfiguration('grid_growth_margin')),
                        ('grid_bounds_snap', LaunchConfiguration('grid_bounds_snap')),
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
            package='go2_slam_nav',
            executable='go2_cloud_throttle',
            name='go2_fast_lio_nav_cloud_filter',
            output='screen',
            parameters=[{
                'input_topic': '/lio_cloud_base',
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
        ),

        TimerAction(
            period=LaunchConfiguration('nav2_start_delay'),
            actions=[
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(
                        PathJoinSubstitution([
                            FindPackageShare('nav2_bringup'),
                            'launch',
                            'navigation_launch.py'
                        ])
                    ),
                    launch_arguments=[
                        ('params_file', LaunchConfiguration('nav2_params_file')),
                        ('use_sim_time', LaunchConfiguration('use_sim_time')),
                        ('autostart', 'true'),
                    ],
                ),
                Node(
                    package='go2_cmd_processor',
                    executable='sport_ctrl',
                    name='sport_ctrl',
                    output='screen',
                    parameters=[{
                        'log_level': 'info',
                        'cmd_vel_topic': LaunchConfiguration('go2_cmd_vel_topic'),
                        'request_topic': LaunchConfiguration('go2_sport_request_topic'),
                        'cmd_vel_timeout': LaunchConfiguration('go2_cmd_timeout'),
                        'max_vx': LaunchConfiguration('go2_cmd_max_vx'),
                        'max_vy': LaunchConfiguration('go2_cmd_max_vy'),
                        'max_wz': LaunchConfiguration('go2_cmd_max_wz'),
                        'request_qos_reliability':
                            LaunchConfiguration('go2_request_qos_reliability'),
                    }],
                    condition=IfCondition(LaunchConfiguration('start_go2_cmd_bridge')),
                ),
                Node(
                    package='go2_slam_nav',
                    executable='go2_goal_pose_bridge',
                    name='go2_goal_pose_bridge',
                    output='screen',
                    parameters=[{
                        'goal_pose_topic': LaunchConfiguration('goal_pose_topic'),
                        'navigate_action_name': LaunchConfiguration('navigate_action_name'),
                        'default_frame_id': 'map',
                    }],
                    condition=IfCondition(LaunchConfiguration('start_goal_pose_bridge')),
                ),
            ],
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
    ])
