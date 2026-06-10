import os
from glob import glob

from setuptools import setup


package_name = "terrain_mapping"

setup(
    name=package_name,
    version="0.0.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "rviz"), glob("rviz/*.rviz")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="star",
    maintainer_email="star@todo.todo",
    description="2.5D terrain perception layer for Go2 FAST-LIO and Nav2.",
    license="TODO: License declaration",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "terrain_mapper_node = terrain_mapping.terrain_mapper_node:main",
        ],
    },
)
