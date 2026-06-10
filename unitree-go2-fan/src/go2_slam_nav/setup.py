from setuptools import setup
import os
from glob import glob

package_name = 'go2_slam_nav'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='bedigital',
    maintainer_email='bedigital@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'go2_cloud_throttle = go2_slam_nav.go2_cloud_throttle:main',
            'go2_joint_state_publisher = go2_slam_nav.go2_joint_state_publisher:main',
            'go2_lowstate_joint_relay = go2_slam_nav.go2_lowstate_joint_relay:main',
            'go2_camera_viewer = go2_slam_nav.go2_camera_viewer:main',
            'go2_marker_publisher = go2_slam_nav.go2_marker_publisher:main',
            'go2_odom_relay = go2_slam_nav.go2_odom_relay:main',
            'go2_cloud_accumulator = go2_slam_nav.go2_cloud_accumulator:main',
            'go2_lio_grid_mapper = go2_slam_nav.go2_lio_grid_mapper:main',
            'go2_lio_points_adapter = go2_slam_nav.go2_lio_points_adapter:main',
            'go2_lio_imu_adapter = go2_slam_nav.go2_lio_imu_adapter:main',
            'go2_visual_urdf = go2_slam_nav.go2_visual_urdf:main',
            'go2_goal_pose_bridge = go2_slam_nav.go2_goal_pose_bridge:main',
        ],
    },
)
