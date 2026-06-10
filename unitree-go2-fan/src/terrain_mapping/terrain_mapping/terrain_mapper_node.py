import math

import numpy as np
import rclpy
from geometry_msgs.msg import Point, Pose
from nav_msgs.msg import MapMetaData, OccupancyGrid
from rclpy.duration import Duration
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    QoSProfile,
    ReliabilityPolicy,
    qos_profile_sensor_data,
)
from rclpy.time import Time
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Header
from tf2_ros import Buffer, TransformException, TransformListener
from visualization_msgs.msg import Marker, MarkerArray


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


def quaternion_to_matrix(q):
    x = q.x
    y = q.y
    z = q.z
    w = q.w
    xx = x * x
    yy = y * y
    zz = z * z
    xy = x * y
    xz = x * z
    yz = y * z
    wx = w * x
    wy = w * y
    wz = w * z
    return np.array(
        [
            [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
            [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
            [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
        ],
        dtype=np.float64,
    )


def transform_to_matrix(transform):
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = quaternion_to_matrix(transform.transform.rotation)
    matrix[0, 3] = transform.transform.translation.x
    matrix[1, 3] = transform.transform.translation.y
    matrix[2, 3] = transform.transform.translation.z
    return matrix


def apply_transform(points, matrix):
    if points.size == 0:
        return points
    return points @ matrix[:3, :3].T + matrix[:3, 3]


class TerrainMapper(Node):
    def __init__(self):
        super().__init__("terrain_mapper")

        self.declare_parameters(
            "",
            [
                ("target_frame", "map"),
                ("base_frame", "base_link"),
                ("use_fastlio_cloud", True),
                ("fastlio_cloud_topic", "/lio_cloud_registered"),
                ("use_map_cloud", True),
                ("map_cloud_topic", "/lio_cloud_map"),
                ("use_d435i_cloud", True),
                ("d435i_cloud_topic", "/camera/depth/color/points"),
                ("d435i_cloud_topic_alt", "/camera/camera/depth/color/points"),
                ("local_map_radius", 5.0),
                ("local_map_forward", 5.0),
                ("local_map_backward", 1.0),
                ("grid_resolution", 0.05),
                ("min_z", -0.40),
                ("max_z", 1.50),
                ("ground_height_min", -0.18),
                ("obstacle_height_min", 0.06),
                ("obstacle_height_max", 1.20),
                ("max_slope_deg", 12.0),
                ("max_step_height", 0.08),
                ("max_roughness", 0.04),
                ("voxel_leaf_size", 0.05),
                ("publish_rate", 4.0),
                ("debug_publish_rate", 2.0),
                ("robot_width", 0.38),
                ("safety_margin", 0.22),
                ("min_points_per_cell", 1),
                ("max_points_per_cloud", 250000),
                ("max_grid_cells", 250000),
                ("tf_timeout", 0.08),
                ("source_timeout", 3.0),
                ("publish_nav2_costmap", True),
                ("inflate_traversability_grid", False),
                ("elevation_map_topic", "/elevation_map"),
                ("elevation_cloud_topic", "/elevation_cloud_debug"),
                ("traversability_grid_topic", "/traversability_grid"),
                ("stair_edges_marker_topic", "/stair_edges_marker"),
                ("terrain_debug_markers_topic", "/terrain_debug_markers"),
                ("terrain_obstacle_cloud_topic", "/terrain_obstacle_cloud"),
                ("nav2_terrain_costmap_topic", "/nav2_terrain_costmap"),
                ("stair_min_step_height", 0.06),
                ("stair_max_step_height", 0.20),
                ("stair_min_edges", 8),
                ("stair_front_min", 0.20),
                ("stair_front_max", 4.0),
                ("stair_lateral_half_width", 1.2),
            ],
        )

        self.target_frame = self.get_parameter("target_frame").value
        self.base_frame = self.get_parameter("base_frame").value
        self.local_map_radius = max(
            0.5, float(self.get_parameter("local_map_radius").value)
        )
        self.local_map_forward = max(
            0.1, float(self.get_parameter("local_map_forward").value)
        )
        self.local_map_backward = max(
            0.0, float(self.get_parameter("local_map_backward").value)
        )
        self.resolution = max(0.02, float(self.get_parameter("grid_resolution").value))
        self.min_z = float(self.get_parameter("min_z").value)
        self.max_z = float(self.get_parameter("max_z").value)
        self.ground_height_min = float(self.get_parameter("ground_height_min").value)
        self.obstacle_height_min = float(
            self.get_parameter("obstacle_height_min").value
        )
        self.obstacle_height_max = float(
            self.get_parameter("obstacle_height_max").value
        )
        self.max_slope_deg = max(0.1, float(self.get_parameter("max_slope_deg").value))
        self.max_step_height = max(
            0.01, float(self.get_parameter("max_step_height").value)
        )
        self.max_roughness = max(0.001, float(self.get_parameter("max_roughness").value))
        self.voxel_leaf_size = max(
            0.01, float(self.get_parameter("voxel_leaf_size").value)
        )
        self.publish_rate = max(0.2, float(self.get_parameter("publish_rate").value))
        self.debug_publish_rate = max(
            0.1, float(self.get_parameter("debug_publish_rate").value)
        )
        self.robot_width = max(0.0, float(self.get_parameter("robot_width").value))
        self.safety_margin = max(0.0, float(self.get_parameter("safety_margin").value))
        self.min_points_per_cell = max(
            1, int(self.get_parameter("min_points_per_cell").value)
        )
        self.max_points_per_cloud = max(
            1000, int(self.get_parameter("max_points_per_cloud").value)
        )
        self.max_grid_cells = max(1000, int(self.get_parameter("max_grid_cells").value))
        self.tf_timeout = max(0.01, float(self.get_parameter("tf_timeout").value))
        self.source_timeout = max(0.1, float(self.get_parameter("source_timeout").value))
        self.publish_nav2_costmap = as_bool(
            self.get_parameter("publish_nav2_costmap").value
        )
        self.inflate_traversability_grid = as_bool(
            self.get_parameter("inflate_traversability_grid").value
        )
        self.stair_min_step_height = max(
            0.01, float(self.get_parameter("stair_min_step_height").value)
        )
        self.stair_max_step_height = max(
            self.stair_min_step_height,
            float(self.get_parameter("stair_max_step_height").value),
        )
        self.stair_min_edges = max(1, int(self.get_parameter("stair_min_edges").value))
        self.stair_front_min = float(self.get_parameter("stair_front_min").value)
        self.stair_front_max = float(self.get_parameter("stair_front_max").value)
        self.stair_lateral_half_width = max(
            0.1, float(self.get_parameter("stair_lateral_half_width").value)
        )

        grid_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        cloud_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        marker_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)

        self.elevation_map_pub = self.create_publisher(
            OccupancyGrid,
            self.get_parameter("elevation_map_topic").value,
            grid_qos,
        )
        self.traversability_pub = self.create_publisher(
            OccupancyGrid,
            self.get_parameter("traversability_grid_topic").value,
            grid_qos,
        )
        self.nav2_costmap_pub = self.create_publisher(
            OccupancyGrid,
            self.get_parameter("nav2_terrain_costmap_topic").value,
            grid_qos,
        )
        self.elevation_cloud_pub = self.create_publisher(
            PointCloud2,
            self.get_parameter("elevation_cloud_topic").value,
            cloud_qos,
        )
        self.obstacle_cloud_pub = self.create_publisher(
            PointCloud2,
            self.get_parameter("terrain_obstacle_cloud_topic").value,
            cloud_qos,
        )
        self.stair_marker_pub = self.create_publisher(
            MarkerArray,
            self.get_parameter("stair_edges_marker_topic").value,
            marker_qos,
        )
        self.debug_marker_pub = self.create_publisher(
            MarkerArray,
            self.get_parameter("terrain_debug_markers_topic").value,
            marker_qos,
        )

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        self.latest_clouds = {}
        self.cloud_subscriptions = []
        self.add_cloud_subscription(
            "fastlio",
            self.get_parameter("fastlio_cloud_topic").value,
            as_bool(self.get_parameter("use_fastlio_cloud").value),
        )
        self.add_cloud_subscription(
            "map_cloud",
            self.get_parameter("map_cloud_topic").value,
            as_bool(self.get_parameter("use_map_cloud").value),
        )
        self.add_cloud_subscription(
            "d435i",
            self.get_parameter("d435i_cloud_topic").value,
            as_bool(self.get_parameter("use_d435i_cloud").value),
        )
        d435i_alt_topic = self.get_parameter("d435i_cloud_topic_alt").value
        if (
            d435i_alt_topic
            and d435i_alt_topic != self.get_parameter("d435i_cloud_topic").value
        ):
            self.add_cloud_subscription(
                "d435i_alt",
                d435i_alt_topic,
                as_bool(self.get_parameter("use_d435i_cloud").value),
            )

        self.received = 0
        self.processed = 0
        self.skipped_no_cloud = 0
        self.skipped_tf = 0
        self.skipped_empty = 0
        self.last_debug_pub_ns = 0
        self.debug_period_ns = int(1e9 / self.debug_publish_rate)

        self.timer = self.create_timer(1.0 / self.publish_rate, self.process_latest)
        self.stats_timer = self.create_timer(10.0, self.report_stats)

        self.get_logger().info(
            "terrain_mapper_node ready: "
            f"target_frame={self.target_frame}, base_frame={self.base_frame}, "
            f"resolution={self.resolution:.2f}, local_forward={self.local_map_forward:.1f}, "
            f"local_radius={self.local_map_radius:.1f}, safety_margin={self.safety_margin:.2f}"
        )

    def add_cloud_subscription(self, source_name, topic, enabled):
        if not enabled:
            self.get_logger().info(f"{source_name} cloud disabled ({topic})")
            return
        sub = self.create_subscription(
            PointCloud2,
            topic,
            lambda msg, name=source_name: self.cloud_callback(name, msg),
            qos_profile_sensor_data,
        )
        self.cloud_subscriptions.append(sub)
        self.get_logger().info(f"Subscribing {source_name} cloud: {topic}")

    def cloud_callback(self, source_name, msg):
        self.received += 1
        self.latest_clouds[source_name] = (msg, self.get_clock().now())

    def process_latest(self):
        now = self.get_clock().now()
        source_msgs = []
        for name, (msg, stamp) in list(self.latest_clouds.items()):
            age = (now - stamp).nanoseconds * 1e-9
            if age <= self.source_timeout:
                source_msgs.append((name, msg))
        if not source_msgs:
            self.skipped_no_cloud += 1
            return

        target_from_base = self.lookup_matrix(self.target_frame, self.base_frame)
        if target_from_base is None:
            self.skipped_tf += 1
            return
        base_from_target = np.linalg.inv(target_from_base)
        base_origin = target_from_base[:3, 3].copy()

        target_chunks = []
        base_chunks = []
        used_sources = []
        source_point_counts = []
        for source_name, msg in source_msgs:
            target_from_source = self.lookup_matrix(
                self.target_frame,
                msg.header.frame_id,
            )
            if target_from_source is None:
                self.skipped_tf += 1
                continue
            points = self.extract_xyz(msg)
            if points.size == 0:
                continue
            used_sources.append(source_name)
            source_point_counts.append(f"{source_name}:{points.shape[0]}")
            target_points = apply_transform(points, target_from_source)
            base_points = apply_transform(target_points, base_from_target)
            target_chunks.append(target_points)
            base_chunks.append(base_points)

        if not target_chunks:
            self.skipped_empty += 1
            return

        target_points = np.vstack(target_chunks)
        base_points = np.vstack(base_chunks)
        local_mask = (
            (base_points[:, 0] >= -self.local_map_backward)
            & (base_points[:, 0] <= self.local_map_forward)
            & (np.abs(base_points[:, 1]) <= self.local_map_radius)
            & (base_points[:, 2] >= self.min_z)
            & (base_points[:, 2] <= self.max_z)
        )
        if not np.any(local_mask):
            self.skipped_empty += 1
            self.publish_empty_outputs(base_origin)
            return

        target_points = target_points[local_mask]
        base_points = base_points[local_mask]
        target_points, base_points = self.voxel_downsample(target_points, base_points)
        result = self.build_terrain_products(
            target_points,
            base_points,
            base_origin,
            base_from_target,
        )
        if result is None:
            self.skipped_empty += 1
            return

        now_msg = now.to_msg()
        self.elevation_map_pub.publish(result["elevation_map"])
        self.traversability_pub.publish(result["traversability_grid"])
        if self.publish_nav2_costmap:
            self.nav2_costmap_pub.publish(result["nav2_costmap"])
        self.obstacle_cloud_pub.publish(result["obstacle_cloud"])

        now_ns = now.nanoseconds
        if now_ns - self.last_debug_pub_ns >= self.debug_period_ns:
            self.elevation_cloud_pub.publish(result["elevation_cloud"])
            self.stair_marker_pub.publish(result["stair_markers"])
            self.debug_marker_pub.publish(
                self.make_debug_markers(now_msg, result["stats"])
            )
            self.last_debug_pub_ns = now_ns

        self.processed += 1

    def lookup_matrix(self, target_frame, source_frame):
        if not source_frame:
            self.get_logger().warn("Received cloud with empty frame_id")
            return None
        if target_frame == source_frame:
            return np.eye(4, dtype=np.float64)
        try:
            tf = self.tf_buffer.lookup_transform(
                target_frame,
                source_frame,
                Time(),
                timeout=Duration(seconds=self.tf_timeout),
            )
        except TransformException as exc:
            self.get_logger().warn(
                f"TF lookup failed {target_frame} <- {source_frame}: {exc}",
                throttle_duration_sec=2.0,
            )
            return None
        return transform_to_matrix(tf)

    def extract_xyz(self, msg):
        try:
            points = point_cloud2.read_points_numpy(
                msg,
                field_names=("x", "y", "z"),
                skip_nans=True,
            )
        except Exception as exc:
            self.get_logger().warn(
                f"Failed to read PointCloud2 xyz fields: {exc}",
                throttle_duration_sec=2.0,
            )
            return np.empty((0, 3), dtype=np.float64)

        if points.size == 0:
            return np.empty((0, 3), dtype=np.float64)
        points = np.asarray(points, dtype=np.float64)
        points = points.reshape((-1, 3))
        if points.shape[0] > self.max_points_per_cloud:
            stride = int(math.ceil(points.shape[0] / self.max_points_per_cloud))
            points = points[::stride]
        finite = np.isfinite(points).all(axis=1)
        return points[finite]

    def voxel_downsample(self, target_points, base_points):
        if target_points.shape[0] == 0 or self.voxel_leaf_size <= 0.0:
            return target_points, base_points
        keys = np.floor(base_points / self.voxel_leaf_size).astype(np.int64)
        _, keep = np.unique(keys, axis=0, return_index=True)
        keep.sort()
        return target_points[keep], base_points[keep]

    def build_terrain_products(self, target_points, base_points, base_origin, base_from_target):
        extent = max(
            self.local_map_radius,
            self.local_map_forward,
            self.local_map_backward,
        ) + self.safety_margin + 0.5
        min_x = float(base_origin[0] - extent)
        max_x = float(base_origin[0] + extent)
        min_y = float(base_origin[1] - extent)
        max_y = float(base_origin[1] + extent)
        width = max(1, int(math.ceil((max_x - min_x) / self.resolution)))
        height = max(1, int(math.ceil((max_y - min_y) / self.resolution)))
        if width * height > self.max_grid_cells:
            self.get_logger().warn(
                f"terrain grid too large ({width}x{height}); reduce radius or resolution",
                throttle_duration_sec=3.0,
            )
            return None

        xs = np.floor((target_points[:, 0] - min_x) / self.resolution).astype(np.int64)
        ys = np.floor((target_points[:, 1] - min_y) / self.resolution).astype(np.int64)
        valid = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
        if not np.any(valid):
            return None

        xs = xs[valid]
        ys = ys[valid]
        target_points = target_points[valid]
        base_points = base_points[valid]
        flat = ys * width + xs
        cell_count = width * height

        count = np.zeros(cell_count, dtype=np.int32)
        sum_z = np.zeros(cell_count, dtype=np.float64)
        sum_z2 = np.zeros(cell_count, dtype=np.float64)
        min_z = np.full(cell_count, np.inf, dtype=np.float64)
        max_z = np.full(cell_count, -np.inf, dtype=np.float64)
        min_base_z = np.full(cell_count, np.inf, dtype=np.float64)
        max_base_z = np.full(cell_count, -np.inf, dtype=np.float64)

        z = target_points[:, 2]
        base_z = base_points[:, 2]
        np.add.at(count, flat, 1)
        np.add.at(sum_z, flat, z)
        np.add.at(sum_z2, flat, z * z)
        np.minimum.at(min_z, flat, z)
        np.maximum.at(max_z, flat, z)
        np.minimum.at(min_base_z, flat, base_z)
        np.maximum.at(max_base_z, flat, base_z)

        known = count >= self.min_points_per_cell
        mean_z = np.zeros(cell_count, dtype=np.float64)
        mean_z[known] = sum_z[known] / count[known]
        roughness = np.zeros(cell_count, dtype=np.float64)
        variance = np.zeros(cell_count, dtype=np.float64)
        variance[known] = sum_z2[known] / count[known] - mean_z[known] ** 2
        roughness[known] = np.sqrt(np.maximum(variance[known], 0.0))
        height_range = np.zeros(cell_count, dtype=np.float64)
        height_range[known] = max_z[known] - min_z[known]
        base_height_range = np.zeros(cell_count, dtype=np.float64)
        base_height_range[known] = max_base_z[known] - min_base_z[known]

        known_2d = known.reshape((height, width))
        mean_2d = mean_z.reshape((height, width))
        slope_2d, step_jump_2d, stair_edge_mask = self.compute_slope_and_steps(
            mean_2d,
            known_2d,
        )

        height_range_2d = height_range.reshape((height, width))
        base_height_range_2d = base_height_range.reshape((height, width))
        roughness_2d = roughness.reshape((height, width))
        max_base_z_2d = max_base_z.reshape((height, width))

        ground_candidate = (
            known_2d
            & (min_base_z.reshape((height, width)) >= self.ground_height_min)
            & (min_base_z.reshape((height, width)) <= self.obstacle_height_min)
        )
        unsafe = (
            ground_candidate
            & (
                (height_range_2d > self.max_step_height)
                | (base_height_range_2d > self.max_step_height)
                | (roughness_2d > self.max_roughness)
                | (slope_2d > self.max_slope_deg)
                | step_jump_2d
            )
        )
        obstacle_by_height = (
            known_2d
            & (max_base_z_2d >= self.obstacle_height_min)
            & (max_base_z_2d <= self.obstacle_height_max)
            & (
                ~ground_candidate
                |
                (base_height_range_2d >= self.obstacle_height_min)
                | (height_range_2d >= self.obstacle_height_min)
            )
        )
        blocked = unsafe | obstacle_by_height
        blocked_inflated = self.dilate_mask(blocked, self.inflation_cells())

        score = np.full((height, width), -1, dtype=np.int16)
        score_known = np.zeros((height, width), dtype=np.float64)
        score_known = np.maximum(
            score_known,
            100.0 * height_range_2d / self.max_step_height,
        )
        score_known = np.maximum(score_known, 100.0 * slope_2d / self.max_slope_deg)
        score_known = np.maximum(score_known, 100.0 * roughness_2d / self.max_roughness)
        score[ground_candidate] = np.clip(
            score_known[ground_candidate],
            0,
            100,
        ).astype(np.int16)
        score[blocked] = 100
        if self.inflate_traversability_grid:
            score[blocked_inflated] = 100

        nav_score = score.copy()
        nav_score[blocked_inflated] = 100

        elevation_grid = self.make_elevation_grid(
            mean_z.reshape((height, width)),
            known_2d,
            min_x,
            min_y,
            width,
            height,
            base_origin[2],
        )
        traversability_grid = self.make_grid(
            score.astype(np.int8),
            min_x,
            min_y,
            width,
            height,
            "traversability",
        )
        nav2_costmap = self.make_grid(
            nav_score.astype(np.int8),
            min_x,
            min_y,
            width,
            height,
            "nav2_terrain_costmap",
        )
        elevation_cloud = self.make_elevation_cloud(
            mean_z.reshape((height, width)),
            known_2d,
            min_x,
            min_y,
        )
        obstacle_cloud = self.make_obstacle_cloud(
            blocked_inflated,
            max_z.reshape((height, width)),
            min_x,
            min_y,
            base_origin[2],
        )
        stair_markers, stair_count = self.make_stair_markers(
            stair_edge_mask,
            mean_z.reshape((height, width)),
            known_2d,
            min_x,
            min_y,
            base_from_target,
        )

        return {
            "elevation_map": elevation_grid,
            "traversability_grid": traversability_grid,
            "nav2_costmap": nav2_costmap,
            "elevation_cloud": elevation_cloud,
            "obstacle_cloud": obstacle_cloud,
            "stair_markers": stair_markers,
            "stats": {
                "known_cells": int(np.count_nonzero(known_2d)),
                "ground_cells": int(np.count_nonzero(ground_candidate)),
                "blocked_cells": int(np.count_nonzero(blocked_inflated)),
                "stair_edges": int(stair_count),
                "points": int(target_points.shape[0]),
                "sources": ", ".join(used_sources) if used_sources else "none",
                "source_points": ", ".join(source_point_counts)
                if source_point_counts
                else "none",
            },
        }

    def compute_slope_and_steps(self, mean_z, known):
        height, width = mean_z.shape
        max_diff = np.zeros_like(mean_z)
        step_jump = np.zeros_like(known, dtype=bool)
        stair_edge = {
            "x": np.zeros((height, max(0, width - 1)), dtype=bool),
            "y": np.zeros((max(0, height - 1), width), dtype=bool),
        }

        if width > 1:
            valid = known[:, :-1] & known[:, 1:]
            diff = np.abs(mean_z[:, 1:] - mean_z[:, :-1])
            max_diff[:, :-1] = np.maximum(max_diff[:, :-1], diff * valid)
            max_diff[:, 1:] = np.maximum(max_diff[:, 1:], diff * valid)
            jump = valid & (diff > self.max_step_height)
            step_jump[:, :-1] |= jump
            step_jump[:, 1:] |= jump
            stair_edge["x"] = (
                valid
                & (diff >= self.stair_min_step_height)
                & (diff <= self.stair_max_step_height)
            )

        if height > 1:
            valid = known[:-1, :] & known[1:, :]
            diff = np.abs(mean_z[1:, :] - mean_z[:-1, :])
            max_diff[:-1, :] = np.maximum(max_diff[:-1, :], diff * valid)
            max_diff[1:, :] = np.maximum(max_diff[1:, :], diff * valid)
            jump = valid & (diff > self.max_step_height)
            step_jump[:-1, :] |= jump
            step_jump[1:, :] |= jump
            stair_edge["y"] = (
                valid
                & (diff >= self.stair_min_step_height)
                & (diff <= self.stair_max_step_height)
            )

        slope_deg = np.degrees(np.arctan2(max_diff, self.resolution))
        return slope_deg, step_jump, stair_edge

    def make_elevation_grid(self, mean_z, known, min_x, min_y, width, height, base_z):
        data = np.full((height, width), -1, dtype=np.int8)
        denom = max(0.01, self.max_z - self.min_z)
        normalized = 100.0 * (mean_z - (base_z + self.min_z)) / denom
        data[known] = np.clip(normalized[known], 0, 100).astype(np.int8)
        return self.make_grid(data, min_x, min_y, width, height, "elevation_map")

    def make_grid(self, data, min_x, min_y, width, height, _name):
        grid = OccupancyGrid()
        grid.header.stamp = self.get_clock().now().to_msg()
        grid.header.frame_id = self.target_frame
        grid.info = MapMetaData()
        grid.info.map_load_time = grid.header.stamp
        grid.info.resolution = self.resolution
        grid.info.width = width
        grid.info.height = height
        grid.info.origin = Pose()
        grid.info.origin.position.x = float(min_x)
        grid.info.origin.position.y = float(min_y)
        grid.info.origin.position.z = 0.0
        grid.info.origin.orientation.w = 1.0
        grid.data = data.reshape(-1).astype(np.int8).tolist()
        return grid

    def make_elevation_cloud(self, mean_z, known, min_x, min_y):
        ys, xs = np.where(known)
        if xs.size == 0:
            return self.make_cloud(np.empty((0, 3), dtype=np.float32))
        points = np.column_stack(
            (
                min_x + (xs.astype(np.float64) + 0.5) * self.resolution,
                min_y + (ys.astype(np.float64) + 0.5) * self.resolution,
                mean_z[ys, xs],
            )
        )
        return self.make_cloud(points)

    def make_obstacle_cloud(self, blocked, max_z, min_x, min_y, base_z):
        ys, xs = np.where(blocked)
        if xs.size == 0:
            return self.make_cloud(np.empty((0, 3), dtype=np.float32))
        z = max_z[ys, xs]
        z = np.where(np.isfinite(z), z, base_z + self.obstacle_height_min)
        points = np.column_stack(
            (
                min_x + (xs.astype(np.float64) + 0.5) * self.resolution,
                min_y + (ys.astype(np.float64) + 0.5) * self.resolution,
                z,
            )
        )
        return self.make_cloud(points)

    def make_cloud(self, points):
        header = Header()
        header.stamp = self.get_clock().now().to_msg()
        header.frame_id = self.target_frame
        points = np.asarray(points, dtype=np.float32).reshape((-1, 3))
        return point_cloud2.create_cloud_xyz32(header, points.tolist())

    def make_stair_markers(self, stair_edge, mean_z, known, min_x, min_y, base_from_target):
        marker_array = MarkerArray()
        clear = Marker()
        clear.action = Marker.DELETEALL
        marker_array.markers.append(clear)

        edge_points = []
        height, width = known.shape

        if width > 1:
            ys, xs = np.where(stair_edge["x"])
            for y, x in zip(ys, xs):
                x_boundary = min_x + (x + 1) * self.resolution
                y0 = min_y + y * self.resolution
                y1 = y0 + self.resolution
                z = max(mean_z[y, x], mean_z[y, x + 1]) + 0.04
                center = np.array([[x_boundary, 0.5 * (y0 + y1), z]], dtype=np.float64)
                if not self.in_stair_search_region(center, base_from_target):
                    continue
                edge_points.extend([Point(x=x_boundary, y=y0, z=z), Point(x=x_boundary, y=y1, z=z)])

        if height > 1:
            ys, xs = np.where(stair_edge["y"])
            for y, x in zip(ys, xs):
                y_boundary = min_y + (y + 1) * self.resolution
                x0 = min_x + x * self.resolution
                x1 = x0 + self.resolution
                z = max(mean_z[y, x], mean_z[y + 1, x]) + 0.04
                center = np.array([[0.5 * (x0 + x1), y_boundary, z]], dtype=np.float64)
                if not self.in_stair_search_region(center, base_from_target):
                    continue
                edge_points.extend([Point(x=x0, y=y_boundary, z=z), Point(x=x1, y=y_boundary, z=z)])

        edge_count = len(edge_points) // 2
        if edge_count < self.stair_min_edges:
            return marker_array, edge_count

        marker = Marker()
        marker.header.stamp = self.get_clock().now().to_msg()
        marker.header.frame_id = self.target_frame
        marker.ns = "stair_edges"
        marker.id = 1
        marker.type = Marker.LINE_LIST
        marker.action = Marker.ADD
        marker.scale.x = 0.045
        marker.color.r = 1.0
        marker.color.g = 0.35
        marker.color.b = 0.0
        marker.color.a = 1.0
        marker.points = edge_points
        marker_array.markers.append(marker)
        return marker_array, edge_count

    def in_stair_search_region(self, target_point, base_from_target):
        base_point = apply_transform(target_point, base_from_target)[0]
        return (
            self.stair_front_min <= base_point[0] <= self.stair_front_max
            and abs(base_point[1]) <= self.stair_lateral_half_width
        )

    def make_debug_markers(self, stamp, stats):
        marker_array = MarkerArray()
        clear = Marker()
        clear.action = Marker.DELETEALL
        marker_array.markers.append(clear)

        marker = Marker()
        marker.header.stamp = stamp
        marker.header.frame_id = self.base_frame
        marker.ns = "terrain_debug"
        marker.id = 1
        marker.type = Marker.TEXT_VIEW_FACING
        marker.action = Marker.ADD
        marker.pose.position.x = 0.8
        marker.pose.position.y = 0.0
        marker.pose.position.z = 0.9
        marker.pose.orientation.w = 1.0
        marker.scale.z = 0.18
        marker.color.r = 0.1
        marker.color.g = 0.9
        marker.color.b = 1.0
        marker.color.a = 1.0
        marker.text = (
            "Terrain 2.5D\n"
            f"sources: {stats['sources']}\n"
            f"points: {stats['points']}\n"
            f"known cells: {stats['known_cells']}\n"
            f"ground cells: {stats['ground_cells']}\n"
            f"blocked cells: {stats['blocked_cells']}\n"
            f"stair edges: {stats['stair_edges']}"
        )
        marker_array.markers.append(marker)
        return marker_array

    def publish_empty_outputs(self, base_origin):
        extent = max(self.local_map_radius, self.local_map_forward) + self.safety_margin
        width = max(1, int(math.ceil(2.0 * extent / self.resolution)))
        height = width
        min_x = float(base_origin[0] - extent)
        min_y = float(base_origin[1] - extent)
        data = np.full((height, width), -1, dtype=np.int8)
        self.elevation_map_pub.publish(
            self.make_grid(data, min_x, min_y, width, height, "elevation_map")
        )
        self.traversability_pub.publish(
            self.make_grid(data, min_x, min_y, width, height, "traversability")
        )
        self.obstacle_cloud_pub.publish(self.make_cloud(np.empty((0, 3), dtype=np.float32)))

    def inflation_cells(self):
        radius = self.robot_width * 0.5 + self.safety_margin
        return int(math.ceil(radius / self.resolution))

    def dilate_mask(self, mask, cells):
        if cells <= 0 or not np.any(mask):
            return mask.copy()
        out = mask.copy()
        height, width = mask.shape
        ys, xs = np.where(mask)
        for dy in range(-cells, cells + 1):
            for dx in range(-cells, cells + 1):
                if dx * dx + dy * dy > cells * cells:
                    continue
                yy = ys + dy
                xx = xs + dx
                valid = (yy >= 0) & (yy < height) & (xx >= 0) & (xx < width)
                out[yy[valid], xx[valid]] = True
        return out

    def report_stats(self):
        if self.received == 0 and self.processed == 0:
            return
        self.get_logger().info(
            "terrain stats: "
            f"received={self.received}, processed={self.processed}, "
            f"skipped_no_cloud={self.skipped_no_cloud}, skipped_tf={self.skipped_tf}, "
            f"skipped_empty={self.skipped_empty}"
        )


def main(args=None):
    rclpy.init(args=args)
    node = TerrainMapper()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            node.destroy_node()
        except (KeyboardInterrupt, ExternalShutdownException):
            pass
        if rclpy.ok():
            try:
                rclpy.shutdown()
            except (KeyboardInterrupt, ExternalShutdownException):
                pass


if __name__ == "__main__":
    main()
