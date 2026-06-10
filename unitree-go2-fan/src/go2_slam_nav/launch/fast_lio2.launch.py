from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import (
    Command,
    LaunchConfiguration,
    PathJoinSubstitution,
    PythonExpression,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    lio_input_topic = PythonExpression([
        "'", LaunchConfiguration('lio_points_topic'), "' if '",
        LaunchConfiguration('use_lio_points_adapter'), "' == 'true' else '",
        LaunchConfiguration('lidar_topic'), "'",
    ])

    return LaunchDescription([
        DeclareLaunchArgument(
            name='use_rviz',
            default_value='true',
            choices=['true', 'false'],
            description='Open RViz with the LIO display config'
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
            name='hesai_config_path',
            default_value=PathJoinSubstitution([
                FindPackageShare('go2_slam_nav'),
                'config',
                'hesai_jt128.yaml'
            ]),
            description='Hesai driver config.yaml path'
        ),
        DeclareLaunchArgument(name='lidar_topic', default_value='/lidar_points'),
        DeclareLaunchArgument(name='lio_points_topic', default_value='/points_raw'),
        DeclareLaunchArgument(
            name='use_lio_points_adapter',
            default_value='false',
            choices=['true', 'false'],
            description=(
                'Use the legacy Python point repacker. Native Hesai C++ input '
                'is faster and is the default.'
            )
        ),
        DeclareLaunchArgument(
            name='lio_points_axis_mode',
            default_value='identity',
            choices=['identity', 'hesai_y_forward_to_ros'],
            description='Normalize Hesai raw point axes before feeding FAST-LIO2'
        ),
        DeclareLaunchArgument(
            name='imu_topic',
            default_value='/lidar_imu',
            description='Use the rigidly mounted, LiDAR-clocked JT128 IMU by default'
        ),
        DeclareLaunchArgument(name='lio_imu_topic', default_value='/imu_lio'),
        DeclareLaunchArgument(
            name='lio_imu_axis_mode',
            default_value='identity',
            choices=['identity', 'unitree_gyro_z_flip', 'unitree_ned_to_ros'],
            description='Normalize Unitree IMU vector axes before feeding FAST-LIO2'
        ),
        DeclareLaunchArgument(name='lio_points_max_rate', default_value='10.0'),
        DeclareLaunchArgument(name='lio_points_stride', default_value='1'),
        DeclareLaunchArgument(name='lio_scan_period', default_value='0.1'),
        DeclareLaunchArgument(name='lio_points_stamp_mode', default_value='input'),
        DeclareLaunchArgument(name='lio_points_use_input_time_field', default_value='true'),
        DeclareLaunchArgument(name='lio_points_filter_enabled', default_value='true'),
        DeclareLaunchArgument(name='lio_points_min_z', default_value='-2.0'),
        DeclareLaunchArgument(name='lio_points_max_z', default_value='3.0'),
        DeclareLaunchArgument(name='lio_points_min_range', default_value='0.20'),
        DeclareLaunchArgument(name='lio_points_max_range', default_value='80.0'),
        DeclareLaunchArgument(name='lio_imu_frame_id', default_value='hesai_lidar'),
        DeclareLaunchArgument(
            name='lio_imu_stamp_mode',
            default_value='monotonic_input',
            choices=['input', 'monotonic_input', 'now'],
            description='Use input IMU stamps, minimally repair duplicates, or stamp on receipt'
        ),
        DeclareLaunchArgument(name='lio_imu_monotonic_stamp_step_ns', default_value='10000'),
        DeclareLaunchArgument(
            name='lio_imu_angular_velocity_scale',
            default_value='0.017453292519943295',
            description='JT128 publishes angular velocity in degree/s; convert to rad/s'
        ),
        DeclareLaunchArgument(
            name='lio_imu_linear_acceleration_scale',
            default_value='9.80665',
            description='JT128 publishes acceleration in g; convert to m/s^2'
        ),
        DeclareLaunchArgument(
            name='publish_lidar_tf',
            default_value='true',
            choices=['true', 'false'],
            description='Publish static base_link to Hesai LiDAR transform'
        ),
        DeclareLaunchArgument(name='lidar_tf_x', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_y', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_z', default_value='0.10'),
        DeclareLaunchArgument(name='lidar_tf_roll', default_value='0.0'),
        DeclareLaunchArgument(name='lidar_tf_pitch', default_value='0.0'),
        DeclareLaunchArgument(
            name='lidar_tf_yaw',
            default_value='-0.22689280275926285',
            description=(
                'JT128 mounting yaw relative to Go2 base_link in radians. '
                'Negative yaw means the LiDAR is rotated clockwise on the robot.'
            )
        ),
        DeclareLaunchArgument(
            name='publish_unitree_imu_tf',
            default_value='false',
            choices=['true', 'false'],
            description='Publish static base_link to an external/Unitree IMU frame'
        ),
        DeclareLaunchArgument(name='unitree_imu_tf_x', default_value='0.0'),
        DeclareLaunchArgument(name='unitree_imu_tf_y', default_value='0.0'),
        DeclareLaunchArgument(name='unitree_imu_tf_z', default_value='0.0'),
        DeclareLaunchArgument(name='unitree_imu_tf_roll', default_value='0.0'),
        DeclareLaunchArgument(name='unitree_imu_tf_pitch', default_value='0.0'),
        DeclareLaunchArgument(name='unitree_imu_tf_yaw', default_value='0.0'),
        DeclareLaunchArgument(
            name='start_unitree_odom_reference',
            default_value='true',
            choices=['true', 'false'],
            description='Publish /odom_unitree_reference for comparing LIO against Go2 odom'
        ),
        DeclareLaunchArgument(name='unitree_odom_topic', default_value='/utlidar/robot_odom'),
        DeclareLaunchArgument(
            name='unitree_reference_odom_topic',
            default_value='/odom_unitree_reference'
        ),
        DeclareLaunchArgument(name='odom_relay_rate', default_value='30.0'),
        DeclareLaunchArgument(
            name='publish_go2_model',
            default_value='true',
            choices=['true', 'false'],
            description='Publish Go2 robot_description and joint states for RViz'
        ),
        DeclareLaunchArgument(
            name='publish_static_joint_states',
            default_value='true',
            choices=['true', 'false'],
            description='Publish a neutral standing pose when no real Go2 joint state exists'
        ),
        DeclareLaunchArgument(
            name='publish_lowstate_joint_states',
            default_value='true',
            choices=['true', 'false'],
            description=(
                'Relay Unitree/go2_ros2_sdk LowState motor positions to /joint_states '
                'when static joint states are disabled'
            )
        ),
        DeclareLaunchArgument(name='lowstate_topic', default_value='/lowstate'),
        DeclareLaunchArgument(name='joint_states_topic', default_value='/joint_states'),
        DeclareLaunchArgument(
            name='robot_model_frame_id',
            default_value='base_link_visual',
            description='Visual-only root frame for the Go2 RobotModel'
        ),
        DeclareLaunchArgument(
            name='robot_model_z_offset',
            default_value='0.28',
            description='Raise the visual RobotModel above base_link without moving LIO TF'
        ),
        DeclareLaunchArgument(
            name='publish_go2_marker',
            default_value='true',
            choices=['true', 'false'],
            description='Publish a visible +X heading arrow independent of RobotModel'
        ),
        DeclareLaunchArgument(name='marker_publish_rate', default_value='5.0'),
        DeclareLaunchArgument(
            name='go2_urdf_path',
            default_value=PathJoinSubstitution([
                FindPackageShare('go2_description'),
                'urdf',
                'go2_description.urdf'
            ]),
        ),
        DeclareLaunchArgument(
            name='start_fast_lio_core',
            default_value='true',
            choices=['true', 'false'],
            description='Start the installed spark_fast_lio FAST-LIO2 core'
        ),
        DeclareLaunchArgument(
            name='fast_lio_config_path',
            default_value=PathJoinSubstitution([
                FindPackageShare('go2_slam_nav'),
                'config',
                'fast_lio2_hesai_jt128.yaml'
            ]),
            description='FAST-LIO2 parameters for spark_fast_lio on Hesai JT128'
        ),
        DeclareLaunchArgument(
            name='publish_lio_odom_viz',
            default_value='false',
            choices=['true', 'false'],
            description='Publish a throttled odometry topic for RViz display only'
        ),
        DeclareLaunchArgument(name='lio_odom_viz_topic', default_value='/lio_odom_viz'),
        DeclareLaunchArgument(name='lio_odom_viz_rate', default_value='30.0'),
        DeclareLaunchArgument(
            name='publish_lio_cloud_map',
            default_value='true',
            choices=['true', 'false'],
            description='Accumulate FAST-LIO registered scans into a light RViz cloud map'
        ),
        DeclareLaunchArgument(name='lio_cloud_map_input_topic', default_value='/lio_cloud_registered'),
        DeclareLaunchArgument(name='lio_cloud_map_topic', default_value='/lio_cloud_map'),
        DeclareLaunchArgument(name='lio_cloud_map_input_rate', default_value='1.0'),
        DeclareLaunchArgument(name='lio_cloud_map_publish_rate', default_value='0.5'),
        DeclareLaunchArgument(name='lio_cloud_map_point_stride', default_value='1'),
        DeclareLaunchArgument(name='lio_cloud_map_voxel_size', default_value='0.10'),
        DeclareLaunchArgument(name='lio_cloud_map_max_points', default_value='250000'),
        DeclareLaunchArgument(
            name='lio_cloud_map_save_service',
            default_value='/save_lio_cloud_map',
            description='Trigger service used to save the accumulated 3D cloud map'
        ),
        DeclareLaunchArgument(
            name='lio_cloud_map_save_dir',
            default_value='/home/star/go2_maps/fast_lio2',
            description='Directory for saved FAST-LIO 3D cloud maps'
        ),
        DeclareLaunchArgument(name='lio_cloud_map_name', default_value='go2_lio_cloud_map'),
        DeclareLaunchArgument(
            name='lio_cloud_map_save_format',
            default_value='pcd',
            description='3D map save format: pcd, ply, or both'
        ),
        DeclareLaunchArgument(
            name='lio_cloud_map_clear_on_start',
            default_value='true',
            choices=['true', 'false'],
            description='Clear the accumulated 3D cloud map when the accumulator starts'
        ),
        DeclareLaunchArgument(
            name='save_lio_cloud_map_on_shutdown',
            default_value='true',
            choices=['true', 'false'],
            description='Save accumulated 3D cloud map when the launch is stopped'
        ),

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
            package='go2_slam_nav',
            executable='go2_lio_points_adapter',
            name='go2_lio_points_adapter',
            output='screen',
            parameters=[{
                'input_topic': LaunchConfiguration('lidar_topic'),
                'output_topic': LaunchConfiguration('lio_points_topic'),
                'axis_mode': LaunchConfiguration('lio_points_axis_mode'),
                'max_rate': LaunchConfiguration('lio_points_max_rate'),
                'point_stride': LaunchConfiguration('lio_points_stride'),
                'scan_period': LaunchConfiguration('lio_scan_period'),
                'stamp_mode': LaunchConfiguration('lio_points_stamp_mode'),
                'use_input_time_field': LaunchConfiguration('lio_points_use_input_time_field'),
                'filter_enabled': LaunchConfiguration('lio_points_filter_enabled'),
                'min_z': LaunchConfiguration('lio_points_min_z'),
                'max_z': LaunchConfiguration('lio_points_max_z'),
                'min_range': LaunchConfiguration('lio_points_min_range'),
                'max_range': LaunchConfiguration('lio_points_max_range'),
            }],
            condition=IfCondition(LaunchConfiguration('use_lio_points_adapter')),
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_lio_imu_adapter',
            name='go2_lio_imu_adapter',
            output='screen',
            parameters=[{
                'input_topic': LaunchConfiguration('imu_topic'),
                'output_topic': LaunchConfiguration('lio_imu_topic'),
                'frame_id': LaunchConfiguration('lio_imu_frame_id'),
                'stamp_mode': LaunchConfiguration('lio_imu_stamp_mode'),
                'monotonic_stamp_step_ns': LaunchConfiguration(
                    'lio_imu_monotonic_stamp_step_ns'
                ),
                'force_monotonic_output': True,
                'axis_mode': LaunchConfiguration('lio_imu_axis_mode'),
                'angular_velocity_scale': LaunchConfiguration('lio_imu_angular_velocity_scale'),
                'linear_acceleration_scale': LaunchConfiguration(
                    'lio_imu_linear_acceleration_scale'
                ),
                'replace_zero_covariance': True,
            }],
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_odom_relay',
            name='go2_lio_unitree_odom_reference',
            output='screen',
            parameters=[{
                'input_topic': LaunchConfiguration('unitree_odom_topic'),
                'output_topic': LaunchConfiguration('unitree_reference_odom_topic'),
                'odom_frame_id': 'odom',
                'base_frame_id': 'base_link',
                'publish_tf': False,
                'max_rate': LaunchConfiguration('odom_relay_rate'),
                'stamp_mode': 'now',
                'flatten_to_2d': True,
                'replace_zero_covariance': True,
            }],
            condition=IfCondition(LaunchConfiguration('start_unitree_odom_reference')),
        ),

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
                '--frame-id', 'base_link',
                '--child-frame-id', 'hesai_lidar',
            ],
            condition=IfCondition(LaunchConfiguration('publish_lidar_tf')),
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
                '--child-frame-id', LaunchConfiguration('lio_imu_frame_id'),
            ],
            condition=IfCondition(LaunchConfiguration('publish_unitree_imu_tf')),
        ),

        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            arguments=[
                '--x', '0.0',
                '--y', '0.0',
                '--z', LaunchConfiguration('robot_model_z_offset'),
                '--roll', '0.0',
                '--pitch', '0.0',
                '--yaw', '0.0',
                '--frame-id', 'base_link',
                '--child-frame-id', LaunchConfiguration('robot_model_frame_id'),
            ],
            condition=IfCondition(LaunchConfiguration('publish_go2_model')),
        ),

        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='go2_lio_robot_state_publisher',
            output='screen',
            parameters=[{
                'robot_description': ParameterValue(
                    Command([
                        'ros2 run go2_slam_nav go2_visual_urdf ',
                        LaunchConfiguration('go2_urdf_path'),
                        ' ',
                        LaunchConfiguration('robot_model_frame_id'),
                    ]),
                    value_type=str,
                ),
                'use_sim_time': LaunchConfiguration('use_sim_time'),
            }],
            condition=IfCondition(LaunchConfiguration('publish_go2_model')),
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_joint_state_publisher',
            name='go2_lio_joint_state_publisher',
            output='screen',
            parameters=[{
                'output_topic': LaunchConfiguration('joint_states_topic'),
            }],
            condition=IfCondition(PythonExpression([
                "'", LaunchConfiguration('publish_go2_model'), "' == 'true' and '",
                LaunchConfiguration('publish_static_joint_states'), "' == 'true'",
            ])),
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_lowstate_joint_relay',
            name='go2_lio_lowstate_joint_relay',
            output='screen',
            parameters=[{
                'lowstate_topic': LaunchConfiguration('lowstate_topic'),
                'output_topic': LaunchConfiguration('joint_states_topic'),
            }],
            condition=IfCondition(PythonExpression([
                "'", LaunchConfiguration('publish_go2_model'), "' == 'true' and '",
                LaunchConfiguration('publish_static_joint_states'), "' == 'false' and '",
                LaunchConfiguration('publish_lowstate_joint_states'), "' == 'true'",
            ])),
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_marker_publisher',
            name='go2_lio_marker_publisher',
            output='screen',
            parameters=[{
                'frame_id': 'base_link',
                'topic': '/go2_marker',
                'publish_rate': LaunchConfiguration('marker_publish_rate'),
            }],
            condition=IfCondition(LaunchConfiguration('publish_go2_marker')),
        ),

        Node(
            package='spark_fast_lio',
            executable='spark_lio_mapping',
            name='spark_fast_lio_mapping',
            output='screen',
            parameters=[
                LaunchConfiguration('fast_lio_config_path'),
                {'use_sim_time': LaunchConfiguration('use_sim_time')},
            ],
            remappings=[
                ('lidar', lio_input_topic),
                ('imu', LaunchConfiguration('lio_imu_topic')),
                ('odometry', '/lio_odom'),
                ('path', '/lio_path'),
                ('cloud_registered', '/lio_cloud_registered'),
                ('cloud_registered_lidar', '/lio_cloud_lidar'),
                ('cloud_registered_body', '/lio_cloud_body'),
                ('cloud_registered_base', '/lio_cloud_base'),
            ],
            condition=IfCondition(LaunchConfiguration('start_fast_lio_core')),
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_odom_relay',
            name='go2_lio_odom_viz_relay',
            output='screen',
            parameters=[{
                'input_topic': '/lio_odom',
                'output_topic': LaunchConfiguration('lio_odom_viz_topic'),
                'odom_frame_id': 'lio_map',
                'base_frame_id': 'base_link',
                'publish_tf': False,
                'max_rate': LaunchConfiguration('lio_odom_viz_rate'),
                'stamp_mode': 'input',
                'flatten_to_2d': False,
                'replace_zero_covariance': False,
            }],
            condition=IfCondition(LaunchConfiguration('publish_lio_odom_viz')),
        ),

        Node(
            package='go2_slam_nav',
            executable='go2_cloud_accumulator',
            name='go2_lio_cloud_map_accumulator',
            output='screen',
            parameters=[{
                'input_topic': LaunchConfiguration('lio_cloud_map_input_topic'),
                'output_topic': LaunchConfiguration('lio_cloud_map_topic'),
                'target_frame': 'lio_map',
                'max_input_rate': LaunchConfiguration('lio_cloud_map_input_rate'),
                'publish_rate': LaunchConfiguration('lio_cloud_map_publish_rate'),
                'point_stride': LaunchConfiguration('lio_cloud_map_point_stride'),
                'voxel_size': LaunchConfiguration('lio_cloud_map_voxel_size'),
                'max_points': LaunchConfiguration('lio_cloud_map_max_points'),
                'min_z': -2.0,
                'max_z': 3.0,
                'min_range': 0.0,
                'max_range': 0.0,
                'clear_on_start': LaunchConfiguration('lio_cloud_map_clear_on_start'),
                'save_service_name': LaunchConfiguration('lio_cloud_map_save_service'),
                'save_dir': LaunchConfiguration('lio_cloud_map_save_dir'),
                'map_name': LaunchConfiguration('lio_cloud_map_name'),
                'save_format': LaunchConfiguration('lio_cloud_map_save_format'),
                'save_on_shutdown': LaunchConfiguration('save_lio_cloud_map_on_shutdown'),
            }],
            condition=IfCondition(LaunchConfiguration('publish_lio_cloud_map')),
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
