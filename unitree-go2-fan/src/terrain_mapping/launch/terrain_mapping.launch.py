from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    default_params = PathJoinSubstitution([
        FindPackageShare("terrain_mapping"),
        "config",
        "terrain_mapping.yaml",
    ])
    default_rviz = PathJoinSubstitution([
        FindPackageShare("terrain_mapping"),
        "rviz",
        "terrain_mapping_debug.rviz",
    ])

    return LaunchDescription([
        DeclareLaunchArgument(
            "use_rviz",
            default_value="true",
            choices=["true", "false"],
            description="Open terrain debug RViz. This launch never starts cmd_vel bridge.",
        ),
        DeclareLaunchArgument(
            "params_file",
            default_value=default_params,
            description="terrain_mapper_node YAML parameter file",
        ),
        DeclareLaunchArgument(
            "rviz_config",
            default_value=default_rviz,
            description="RViz config for terrain_mapping debug displays",
        ),
        DeclareLaunchArgument(
            "publish_d435i_static_tf",
            default_value="true",
            choices=["true", "false"],
            description="Publish an approximate base_link -> camera_link TF for D435i terrain fusion.",
        ),
        DeclareLaunchArgument("d435i_base_frame", default_value="base_link"),
        DeclareLaunchArgument("d435i_frame_id", default_value="camera_link"),
        DeclareLaunchArgument("d435i_tf_x", default_value="0.30"),
        DeclareLaunchArgument("d435i_tf_y", default_value="0.0"),
        DeclareLaunchArgument("d435i_tf_z", default_value="0.22"),
        DeclareLaunchArgument("d435i_tf_roll", default_value="0.0"),
        DeclareLaunchArgument("d435i_tf_pitch", default_value="0.0"),
        DeclareLaunchArgument("d435i_tf_yaw", default_value="0.0"),
        Node(
            package="terrain_mapping",
            executable="terrain_mapper_node",
            name="terrain_mapper",
            output="screen",
            parameters=[LaunchConfiguration("params_file")],
        ),
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            arguments=[
                "--x",
                LaunchConfiguration("d435i_tf_x"),
                "--y",
                LaunchConfiguration("d435i_tf_y"),
                "--z",
                LaunchConfiguration("d435i_tf_z"),
                "--roll",
                LaunchConfiguration("d435i_tf_roll"),
                "--pitch",
                LaunchConfiguration("d435i_tf_pitch"),
                "--yaw",
                LaunchConfiguration("d435i_tf_yaw"),
                "--frame-id",
                LaunchConfiguration("d435i_base_frame"),
                "--child-frame-id",
                LaunchConfiguration("d435i_frame_id"),
            ],
            condition=IfCondition(LaunchConfiguration("publish_d435i_static_tf")),
        ),
        Node(
            package="rviz2",
            executable="rviz2",
            arguments=["-d", LaunchConfiguration("rviz_config")],
            condition=IfCondition(LaunchConfiguration("use_rviz")),
        ),
    ])
