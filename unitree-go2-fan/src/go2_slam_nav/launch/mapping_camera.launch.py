from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.substitutions import PathJoinSubstitution, LaunchConfiguration
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
## modified by Rahul Roy

def generate_launch_description():
    return LaunchDescription([

        DeclareLaunchArgument(
            name='publish_static_tf',
            default_value='true',
            choices=['true', 'false'],
            description='Publish a static transform between base_link and base_laser for standalone use of this launch file.'
        ),

        DeclareLaunchArgument(
            name='use_rtabmapviz',
            default_value='false',  # suppress incessant VTK 9.0 warnings
            choices=['true', 'false'],
            description='Start rtabmapviz node'
        ),

        DeclareLaunchArgument(
            name='localize_only',
            default_value='false',
            choices=['true', 'false'],
            description='Localize only, do not change loaded map'
        ),

        DeclareLaunchArgument(
            name='restart_map',
            default_value='false',
            choices=['true', 'false'],
            description='Delete previous map and restart'
        ),

        DeclareLaunchArgument(
            name='icp_odometry_log_level',
            default_value='WARN',  # reduce output from this node
            choices=['ERROR', 'WARN', 'INFO', 'DEBUG'],
            description='Set logger level for icp_odometry. Can set to WARN to reduce message output from this node.'
        ),

        DeclareLaunchArgument(
            name='use_rviz',
            default_value='true',
            choices=['true', 'false'],
            description='Open RVIZ for visualization'
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
            name='lidar_frame_id',
            default_value='hesai_lidar',
            description='Frame id used by Hesai point clouds'
        ),
        DeclareLaunchArgument(
            name='publish_lidar_tf',
            default_value='true',
            choices=['true', 'false'],
            description='Publish static base_link to Hesai LiDAR transform'
        ),
        DeclareLaunchArgument(
            name='use_cloud_assembler',
            default_value='false',
            choices=['true', 'false'],
            description='Assemble ICP filtered clouds before RTAB-Map'
        ),
        DeclareLaunchArgument(
            name='rtabmap_scan_cloud_topic',
            default_value='odom_filtered_input_scan',
            description='PointCloud2 topic consumed by RTAB-Map after ICP odometry'
        ),
        DeclareLaunchArgument(
            name='publish_go2_marker',
            default_value='true',
            choices=['true', 'false'],
            description='Publish a visible Go2 body marker in RViz'
        ),

        # Publish a static transform between base_link and base_laser for standalone use
        # of this launch file
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            arguments=['--frame-id', 'base_link',
                       '--child-frame-id', 'base_laser'],
            condition=IfCondition(LaunchConfiguration('publish_static_tf')),
        ),
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            arguments=['--x', '0.0',
                       '--y', '0.0',
                       '--z', '0.10',
                       '--roll', '0.0',
                       '--pitch', '0.0',
                       '--yaw', '0.0',
                       '--frame-id', 'base_link',
                       '--child-frame-id', LaunchConfiguration('lidar_frame_id')],
            condition=IfCondition(LaunchConfiguration('publish_lidar_tf')),
        ),
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            arguments=['--frame-id', 'base_laser',
                       '--child-frame-id', 'camera_link'],
        ),
        Node(
            package='tf2_ros', executable='static_transform_publisher', output='screen',
            arguments=['0', '0', '0', '0', '0', '0', 'camera_gyro_optical_frame', 'camera_imu_optical_frame']),

        Node(
            package='imu_filter_madgwick', executable='imu_filter_madgwick_node', output='screen',
            parameters=[{'use_mag': False,
                         'world_frame': 'enu',
                         'publish_tf': False}],
            remappings=[('imu/data_raw', '/camera/imu')]),


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
            executable='go2_marker_publisher',
            name='go2_marker_publisher',
            output='screen',
            parameters=[{
                'frame_id': 'base_link',
                'topic': '/go2_marker',
            }],
            condition=IfCondition(LaunchConfiguration('publish_go2_marker')),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([
                    FindPackageShare('go2_slam_nav'),
                    'launch',
                    'rtab_camera_lidar.launch.py'
                ])
            ),
            launch_arguments=[
                ('use_rtabmapviz', LaunchConfiguration('use_rtabmapviz')),
                ('icp_odometry_log_level', LaunchConfiguration(
                    'icp_odometry_log_level')),
                ('localize_only', LaunchConfiguration('localize_only')),
                ('restart_map', LaunchConfiguration('restart_map')),
                ('lidar_topic', LaunchConfiguration('lidar_topic')),
                ('lidar_frame_id', LaunchConfiguration('lidar_frame_id')),
                ('use_cloud_assembler', LaunchConfiguration('use_cloud_assembler')),
                ('rtabmap_scan_cloud_topic', LaunchConfiguration('rtabmap_scan_cloud_topic')),
            ],
        ),
    ])
