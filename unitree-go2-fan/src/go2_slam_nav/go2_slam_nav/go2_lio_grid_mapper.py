import math
import os
from datetime import datetime
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

import rclpy
from geometry_msgs.msg import Pose
from nav_msgs.msg import MapMetaData, OccupancyGrid
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import PointCloud2, PointField
from std_srvs.srv import Trigger


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


class Go2LioGridMapper(Node):
    def __init__(self):
        super().__init__("go2_lio_grid_mapper")

        self.declare_parameter("input_topic", "/lio_cloud_map")
        self.declare_parameter("map_topic", "/map")
        self.declare_parameter("map_frame_id", "map")
        self.declare_parameter("resolution", 0.05)
        self.declare_parameter("publish_rate", 1.0)
        self.declare_parameter("map_padding", 1.0)
        self.declare_parameter("stable_bounds", True)
        self.declare_parameter("growth_margin", 2.0)
        self.declare_parameter("bounds_snap", 1.0)
        self.declare_parameter("unknown_as_free", True)
        self.declare_parameter("obstacle_min_z", 0.18)
        self.declare_parameter("obstacle_max_z", 1.60)
        self.declare_parameter("min_obstacle_points", 1)
        self.declare_parameter("obstacle_dilation_radius", 0.05)
        self.declare_parameter("clear_robot_radius", 0.45)
        self.declare_parameter("max_cells", 4000000)
        self.declare_parameter("save_service_name", "/save_lio_2d_map")
        self.declare_parameter("save_dir", "/home/star/go2_maps/fast_lio2")
        self.declare_parameter("map_name", "go2_lio_2d_map")
        self.declare_parameter("save_on_shutdown", False)

        self.input_topic = self.get_parameter("input_topic").value
        self.map_topic = self.get_parameter("map_topic").value
        self.map_frame_id = self.get_parameter("map_frame_id").value
        self.resolution = max(0.01, float(self.get_parameter("resolution").value))
        self.publish_rate = max(0.1, float(self.get_parameter("publish_rate").value))
        self.map_padding = max(0.0, float(self.get_parameter("map_padding").value))
        self.stable_bounds = as_bool(self.get_parameter("stable_bounds").value)
        self.growth_margin = max(0.0, float(self.get_parameter("growth_margin").value))
        self.bounds_snap = max(self.resolution, float(self.get_parameter("bounds_snap").value))
        self.unknown_as_free = as_bool(self.get_parameter("unknown_as_free").value)
        self.obstacle_min_z = float(self.get_parameter("obstacle_min_z").value)
        self.obstacle_max_z = float(self.get_parameter("obstacle_max_z").value)
        self.min_obstacle_points = max(
            1,
            int(self.get_parameter("min_obstacle_points").value),
        )
        self.obstacle_dilation_radius = max(
            0.0,
            float(self.get_parameter("obstacle_dilation_radius").value),
        )
        self.clear_robot_radius = max(
            0.0,
            float(self.get_parameter("clear_robot_radius").value),
        )
        self.max_cells = max(1000, int(self.get_parameter("max_cells").value))
        self.save_service_name = self.get_parameter("save_service_name").value
        self.save_dir = Path(os.path.expanduser(self.get_parameter("save_dir").value))
        self.map_name = self.sanitize_filename(self.get_parameter("map_name").value)
        self.save_on_shutdown = as_bool(self.get_parameter("save_on_shutdown").value)

        self.last_cloud = None
        self.last_grid = None
        self.received = 0
        self.published = 0
        self.skipped_empty = 0
        self.skipped_too_large = 0
        self.bounds = None
        self.bounds_expansions = 0
        self.bad_fields_reported = False
        self.no_numpy_reported = False

        sub_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)
        pub_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.publisher = self.create_publisher(OccupancyGrid, self.map_topic, pub_qos)
        self.subscription = self.create_subscription(
            PointCloud2,
            self.input_topic,
            self.cloud_callback,
            sub_qos,
        )
        self.save_service = self.create_service(
            Trigger,
            self.save_service_name,
            self.handle_save_request,
        )
        self.publish_timer = self.create_timer(1.0 / self.publish_rate, self.publish_map)
        self.stats_timer = self.create_timer(10.0, self.report_stats)

        self.get_logger().info(
            f"Projecting {self.input_topic} -> {self.map_topic}, "
            f"frame={self.map_frame_id}, resolution={self.resolution:.3f} m, "
            f"obstacle_z=[{self.obstacle_min_z:.2f}, {self.obstacle_max_z:.2f}], "
            f"unknown_as_free={self.unknown_as_free}, stable_bounds={self.stable_bounds}, "
            f"save_service={self.save_service_name}, save_dir={self.save_dir}"
        )

    def cloud_callback(self, msg):
        self.received += 1
        self.last_cloud = msg

    def publish_map(self):
        if self.last_cloud is None:
            return
        if np is None:
            if not self.no_numpy_reported:
                self.get_logger().error("numpy is required for go2_lio_grid_mapper")
                self.no_numpy_reported = True
            return

        grid = self.build_grid(self.last_cloud)
        if grid is None:
            return

        self.last_grid = grid
        self.publisher.publish(grid)
        self.published += 1

    def build_grid(self, msg):
        offsets = self.field_offsets(msg)
        if offsets is None:
            if not self.bad_fields_reported:
                self.get_logger().warn("PointCloud2 has no float32 x/y/z fields.")
                self.bad_fields_reported = True
            return None

        points = self.extract_xyz(msg, offsets)
        if points.size == 0:
            self.skipped_empty += 1
            return None

        raw_min_x = float(np.min(points[:, 0]) - self.map_padding)
        raw_max_x = float(np.max(points[:, 0]) + self.map_padding)
        raw_min_y = float(np.min(points[:, 1]) - self.map_padding)
        raw_max_y = float(np.max(points[:, 1]) + self.map_padding)
        min_x, max_x, min_y, max_y = self.map_bounds(
            raw_min_x,
            raw_max_x,
            raw_min_y,
            raw_max_y,
        )
        width = max(1, int(math.ceil((max_x - min_x) / self.resolution)))
        height = max(1, int(math.ceil((max_y - min_y) / self.resolution)))
        if width * height > self.max_cells:
            self.skipped_too_large += 1
            if self.skipped_too_large <= 3:
                self.get_logger().warn(
                    f"Projected map is too large ({width}x{height}); "
                    f"increase resolution or reduce map span."
                )
            return None

        fill_value = 0 if self.unknown_as_free else -1
        data = np.full((height, width), fill_value, dtype=np.int8)

        obstacle_mask = (
            (points[:, 2] >= self.obstacle_min_z)
            & (points[:, 2] <= self.obstacle_max_z)
        )
        obstacle_points = points[obstacle_mask]
        if obstacle_points.size:
            xs = np.floor((obstacle_points[:, 0] - min_x) / self.resolution).astype(np.int64)
            ys = np.floor((obstacle_points[:, 1] - min_y) / self.resolution).astype(np.int64)
            valid = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
            counts = np.zeros((height, width), dtype=np.uint16)
            np.add.at(counts, (ys[valid], xs[valid]), 1)
            data[counts >= self.min_obstacle_points] = 100
            self.dilate_obstacles(data)

        self.clear_robot_footprint(data, min_x, min_y)

        grid = OccupancyGrid()
        grid.header.stamp = self.get_clock().now().to_msg()
        grid.header.frame_id = self.map_frame_id
        grid.info = MapMetaData()
        grid.info.map_load_time = grid.header.stamp
        grid.info.resolution = self.resolution
        grid.info.width = width
        grid.info.height = height
        grid.info.origin = Pose()
        grid.info.origin.position.x = min_x
        grid.info.origin.position.y = min_y
        grid.info.origin.position.z = 0.0
        grid.info.origin.orientation.w = 1.0
        grid.data = data.reshape(-1).astype(np.int8).tolist()
        return grid

    def map_bounds(self, min_x, max_x, min_y, max_y):
        if not self.stable_bounds:
            return min_x, max_x, min_y, max_y

        if self.bounds is None:
            self.bounds = self.expanded_bounds(min_x, max_x, min_y, max_y)
            self.bounds_expansions += 1
            self.log_bounds("initialized")
            return self.bounds

        cur_min_x, cur_max_x, cur_min_y, cur_max_y = self.bounds
        next_min_x = cur_min_x
        next_max_x = cur_max_x
        next_min_y = cur_min_y
        next_max_y = cur_max_y

        if min_x < cur_min_x:
            next_min_x = self.snap_down(min_x - self.growth_margin)
        if max_x > cur_max_x:
            next_max_x = self.snap_up(max_x + self.growth_margin)
        if min_y < cur_min_y:
            next_min_y = self.snap_down(min_y - self.growth_margin)
        if max_y > cur_max_y:
            next_max_y = self.snap_up(max_y + self.growth_margin)

        if (
            next_min_x != cur_min_x
            or next_max_x != cur_max_x
            or next_min_y != cur_min_y
            or next_max_y != cur_max_y
        ):
            self.bounds = (next_min_x, next_max_x, next_min_y, next_max_y)
            self.bounds_expansions += 1
            self.log_bounds("expanded")

        return self.bounds

    def expanded_bounds(self, min_x, max_x, min_y, max_y):
        return (
            self.snap_down(min_x - self.growth_margin),
            self.snap_up(max_x + self.growth_margin),
            self.snap_down(min_y - self.growth_margin),
            self.snap_up(max_y + self.growth_margin),
        )

    def snap_down(self, value):
        return math.floor(value / self.bounds_snap) * self.bounds_snap

    def snap_up(self, value):
        return math.ceil(value / self.bounds_snap) * self.bounds_snap

    def log_bounds(self, action):
        min_x, max_x, min_y, max_y = self.bounds
        width = int(math.ceil((max_x - min_x) / self.resolution))
        height = int(math.ceil((max_y - min_y) / self.resolution))
        self.get_logger().info(
            f"stable map bounds {action}: origin=({min_x:.2f}, {min_y:.2f}), "
            f"size={width}x{height} cells, span=({max_x - min_x:.2f}, {max_y - min_y:.2f}) m"
        )

    def dilate_obstacles(self, data):
        radius_cells = int(math.ceil(self.obstacle_dilation_radius / self.resolution))
        if radius_cells <= 0:
            return

        occupied_y, occupied_x = np.where(data == 100)
        if occupied_x.size == 0:
            return

        height, width = data.shape
        radius_sq = radius_cells * radius_cells
        for dy in range(-radius_cells, radius_cells + 1):
            for dx in range(-radius_cells, radius_cells + 1):
                if dx * dx + dy * dy > radius_sq:
                    continue
                xs = np.clip(occupied_x + dx, 0, width - 1)
                ys = np.clip(occupied_y + dy, 0, height - 1)
                data[ys, xs] = 100

    def clear_robot_footprint(self, data, min_x, min_y):
        if self.clear_robot_radius <= 0.0:
            return

        height, width = data.shape
        cx = int(round((0.0 - min_x) / self.resolution))
        cy = int(round((0.0 - min_y) / self.resolution))
        radius_cells = int(math.ceil(self.clear_robot_radius / self.resolution))
        radius_sq = radius_cells * radius_cells

        for dy in range(-radius_cells, radius_cells + 1):
            y = cy + dy
            if y < 0 or y >= height:
                continue
            for dx in range(-radius_cells, radius_cells + 1):
                if dx * dx + dy * dy > radius_sq:
                    continue
                x = cx + dx
                if 0 <= x < width:
                    data[y, x] = 0

    def field_offsets(self, msg):
        offsets = {}
        for field in msg.fields:
            if field.datatype == PointField.FLOAT32:
                offsets[field.name] = field.offset
        if not {"x", "y", "z"}.issubset(offsets):
            return None
        return offsets

    def extract_xyz(self, msg, offsets):
        point_count = msg.width * msg.height
        if point_count == 0:
            return np.empty((0, 3), dtype=np.float32)

        endian = ">" if msg.is_bigendian else "<"
        dtype = np.dtype({
            "names": ("x", "y", "z"),
            "formats": (endian + "f4", endian + "f4", endian + "f4"),
            "offsets": (offsets["x"], offsets["y"], offsets["z"]),
            "itemsize": msg.point_step,
        })
        cloud = np.frombuffer(msg.data, dtype=dtype, count=point_count)
        x = cloud["x"]
        y = cloud["y"]
        z = cloud["z"]
        mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
        if not np.any(mask):
            return np.empty((0, 3), dtype=np.float32)
        return np.stack((x[mask], y[mask], z[mask]), axis=1).astype(np.float32)

    def handle_save_request(self, request, response):
        del request
        if self.last_grid is None:
            response.success = False
            response.message = "no OccupancyGrid has been published yet"
            return response

        try:
            yaml_path, pgm_path = self.save_grid(self.last_grid)
        except OSError as exc:
            response.success = False
            response.message = f"failed to save 2D map: {exc}"
            return response

        response.success = True
        response.message = f"saved {yaml_path} and {pgm_path}"
        return response

    def save_grid(self, grid):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"{self.map_name}_{stamp}"
        self.save_dir.mkdir(parents=True, exist_ok=True)
        pgm_path = self.save_dir / f"{stem}.pgm"
        yaml_path = self.save_dir / f"{stem}.yaml"
        self.write_pgm(pgm_path, grid)
        self.write_yaml(yaml_path, pgm_path.name, grid)
        self.get_logger().info(f"saved 2D occupancy map to {yaml_path}")
        return yaml_path, pgm_path

    def write_pgm(self, path, grid):
        values = np.asarray(grid.data, dtype=np.int16).reshape(
            (grid.info.height, grid.info.width)
        )
        pixels = np.full(values.shape, 205, dtype=np.uint8)
        pixels[values == 0] = 254
        pixels[values >= 65] = 0
        pixels_to_write = np.flipud(pixels)

        with path.open("wb") as stream:
            stream.write(f"P5\n{grid.info.width} {grid.info.height}\n255\n".encode("ascii"))
            stream.write(pixels_to_write.tobytes())

    def write_yaml(self, path, image_name, grid):
        origin = grid.info.origin.position
        text = (
            f"image: {image_name}\n"
            "mode: trinary\n"
            f"resolution: {grid.info.resolution:.6f}\n"
            f"origin: [{origin.x:.6f}, {origin.y:.6f}, 0.000000]\n"
            "negate: 0\n"
            "occupied_thresh: 0.65\n"
            "free_thresh: 0.25\n"
        )
        path.write_text(text, encoding="ascii")

    def report_stats(self):
        if self.received == 0 and self.published == 0:
            return
        self.get_logger().info(
            f"grid mapper stats: received={self.received}, published={self.published}, "
            f"skipped_empty={self.skipped_empty}, skipped_too_large={self.skipped_too_large}, "
            f"bounds_expansions={self.bounds_expansions}"
        )

    def sanitize_filename(self, value):
        text = str(value).strip()
        safe = []
        for character in text:
            if character.isalnum() or character in ("-", "_", "."):
                safe.append(character)
            else:
                safe.append("_")
        return "".join(safe).strip("._") or "lio_2d_map"


def main(args=None):
    rclpy.init(args=args)
    node = Go2LioGridMapper()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node.save_on_shutdown and node.last_grid is not None:
            try:
                node.save_grid(node.last_grid)
            except OSError as exc:
                node.get_logger().error(f"shutdown 2D map save failed: {exc}")
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
