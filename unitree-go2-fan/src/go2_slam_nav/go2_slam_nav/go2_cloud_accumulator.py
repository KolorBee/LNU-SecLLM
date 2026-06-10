import math
import os
from datetime import datetime
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

import rclpy
from builtin_interfaces.msg import Time
from rclpy.duration import Duration
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import PointCloud2, PointField
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformException, TransformListener


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


class Go2CloudAccumulator(Node):
    def __init__(self):
        super().__init__("go2_cloud_accumulator")

        self.declare_parameter("input_topic", "/lidar_points_slam")
        self.declare_parameter("output_topic", "/visual_cloud_map")
        self.declare_parameter("target_frame", "map")
        self.declare_parameter("max_input_rate", 1.0)
        self.declare_parameter("publish_rate", 0.5)
        self.declare_parameter("point_stride", 4)
        self.declare_parameter("voxel_size", 0.08)
        self.declare_parameter("max_points", 150000)
        self.declare_parameter("min_z", -0.40)
        self.declare_parameter("max_z", 2.20)
        self.declare_parameter("min_range", 0.20)
        self.declare_parameter("max_range", 8.0)
        self.declare_parameter("clear_on_start", True)
        self.declare_parameter("save_service_name", "/save_visual_cloud_map")
        self.declare_parameter("save_dir", "/home/star/go2_maps")
        self.declare_parameter("map_name", "visual_cloud_map")
        self.declare_parameter("save_format", "pcd")
        self.declare_parameter("save_on_shutdown", False)

        self.input_topic = self.get_parameter("input_topic").value
        self.output_topic = self.get_parameter("output_topic").value
        self.target_frame = self.get_parameter("target_frame").value
        self.max_input_rate = float(self.get_parameter("max_input_rate").value)
        self.publish_rate = float(self.get_parameter("publish_rate").value)
        self.point_stride = max(1, int(self.get_parameter("point_stride").value))
        self.voxel_size = max(0.01, float(self.get_parameter("voxel_size").value))
        self.max_points = max(1000, int(self.get_parameter("max_points").value))
        self.min_z = float(self.get_parameter("min_z").value)
        self.max_z = float(self.get_parameter("max_z").value)
        self.min_range = max(0.0, float(self.get_parameter("min_range").value))
        self.max_range = max(0.0, float(self.get_parameter("max_range").value))
        self.clear_on_start = as_bool(self.get_parameter("clear_on_start").value)
        self.save_service_name = self.get_parameter("save_service_name").value
        self.save_dir = Path(os.path.expanduser(self.get_parameter("save_dir").value))
        self.map_name = self.sanitize_filename(self.get_parameter("map_name").value)
        self.save_format = str(self.get_parameter("save_format").value).lower()
        self.save_on_shutdown = as_bool(self.get_parameter("save_on_shutdown").value)

        self.min_input_period_ns = (
            int(1e9 / self.max_input_rate) if self.max_input_rate > 0.0 else 0
        )
        self.decimate_offset = 0
        self.last_input_ns = None
        self.received = 0
        self.integrated = 0
        self.skipped_rate = 0
        self.skipped_tf = 0
        self.bad_fields_reported = False
        self.no_numpy_reported = False
        self.voxels = {}

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        sub_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)
        pub_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.publisher = self.create_publisher(PointCloud2, self.output_topic, pub_qos)
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

        publish_period = 1.0 / self.publish_rate if self.publish_rate > 0.0 else 2.0
        self.publish_timer = self.create_timer(publish_period, self.publish_map)
        self.stats_timer = self.create_timer(10.0, self.report_stats)

        if self.clear_on_start:
            self.voxels.clear()

        self.get_logger().info(
            f"Accumulating visual cloud {self.input_topic} -> {self.output_topic}, "
            f"target_frame={self.target_frame}, input_rate={self.max_input_rate:.2f} Hz, "
            f"publish_rate={self.publish_rate:.2f} Hz, stride={self.point_stride}, "
            f"voxel={self.voxel_size:.3f} m, max_points={self.max_points}, "
            f"save_service={self.save_service_name}, save_dir={self.save_dir}, "
            f"save_format={self.save_format}, save_on_shutdown={self.save_on_shutdown}"
        )

    def cloud_callback(self, msg):
        self.received += 1
        if np is None:
            if not self.no_numpy_reported:
                self.get_logger().error("numpy is required for go2_cloud_accumulator")
                self.no_numpy_reported = True
            return

        now_ns = self.get_clock().now().nanoseconds
        if self.last_input_ns is not None and self.min_input_period_ns > 0:
            if now_ns - self.last_input_ns < self.min_input_period_ns:
                self.skipped_rate += 1
                return
        self.last_input_ns = now_ns

        offsets = self.field_offsets(msg)
        if offsets is None:
            if not self.bad_fields_reported:
                self.get_logger().warn(
                    "PointCloud2 has no float32 x/y/z fields; cannot accumulate."
                )
                self.bad_fields_reported = True
            return

        try:
            transform = self.tf_buffer.lookup_transform(
                self.target_frame,
                msg.header.frame_id,
                Time(),
                timeout=Duration(seconds=0.2),
            )
        except TransformException as exc:
            self.skipped_tf += 1
            if self.skipped_tf <= 3:
                self.get_logger().warn(
                    f"Waiting for TF {self.target_frame} <- {msg.header.frame_id}: {exc}"
                )
            return

        points, intensity = self.extract_points(msg, offsets)
        if points.size == 0:
            return

        points = self.transform_points(points, transform)
        self.insert_voxels(points, intensity)
        self.integrated += 1
        self.decimate_offset = (self.decimate_offset + 1) % self.point_stride

    def field_offsets(self, msg):
        offsets = {}
        for field in msg.fields:
            if field.datatype == PointField.FLOAT32:
                offsets[field.name] = field.offset
        if not {"x", "y", "z"}.issubset(offsets):
            return None
        return offsets

    def extract_points(self, msg, offsets):
        point_count = msg.width * msg.height
        if point_count == 0:
            return np.empty((0, 3), dtype=np.float32), np.empty((0,), dtype=np.float32)

        start = self.decimate_offset if self.decimate_offset < point_count else 0
        indices = np.arange(start, point_count, self.point_stride, dtype=np.int64)
        if indices.size == 0:
            return np.empty((0, 3), dtype=np.float32), np.empty((0,), dtype=np.float32)

        endian = ">" if msg.is_bigendian else "<"
        names = ["x", "y", "z"]
        formats = [endian + "f4", endian + "f4", endian + "f4"]
        field_offsets = [offsets["x"], offsets["y"], offsets["z"]]
        has_intensity = "intensity" in offsets
        if has_intensity:
            names.append("intensity")
            formats.append(endian + "f4")
            field_offsets.append(offsets["intensity"])

        dtype = np.dtype({
            "names": names,
            "formats": formats,
            "offsets": field_offsets,
            "itemsize": msg.point_step,
        })
        cloud = np.frombuffer(msg.data, dtype=dtype, count=point_count)
        x = cloud["x"][indices]
        y = cloud["y"][indices]
        z = cloud["z"][indices]
        mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
        mask &= (z >= self.min_z) & (z <= self.max_z)

        range_sq = x * x + y * y + z * z
        if self.min_range > 0.0:
            mask &= range_sq >= self.min_range * self.min_range
        if self.max_range > 0.0:
            mask &= range_sq <= self.max_range * self.max_range

        if not np.any(mask):
            return np.empty((0, 3), dtype=np.float32), np.empty((0,), dtype=np.float32)

        selected = indices[mask]
        points = np.stack(
            (cloud["x"][selected], cloud["y"][selected], cloud["z"][selected]),
            axis=1,
        ).astype(np.float32, copy=False)
        if has_intensity:
            intensity = cloud["intensity"][selected].astype(np.float32, copy=False)
        else:
            intensity = points[:, 2].astype(np.float32, copy=False)
        return points, intensity

    def transform_points(self, points, transform):
        t = transform.transform.translation
        q = transform.transform.rotation
        rotation = self.quaternion_matrix(q.x, q.y, q.z, q.w)
        translation = np.array([t.x, t.y, t.z], dtype=np.float32)
        return points @ rotation.T + translation

    def quaternion_matrix(self, x, y, z, w):
        norm = math.sqrt(x * x + y * y + z * z + w * w)
        if norm == 0.0:
            return np.eye(3, dtype=np.float32)
        x /= norm
        y /= norm
        z /= norm
        w /= norm
        xx = x * x
        yy = y * y
        zz = z * z
        xy = x * y
        xz = x * z
        yz = y * z
        wx = w * x
        wy = w * y
        wz = w * z
        return np.array([
            [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
            [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
            [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
        ], dtype=np.float32)

    def insert_voxels(self, points, intensity):
        keys = np.floor(points / self.voxel_size).astype(np.int64)
        _, unique_indices = np.unique(keys, axis=0, return_index=True)
        for index in unique_indices:
            key = tuple(int(value) for value in keys[index])
            x, y, z = points[index]
            self.voxels[key] = (
                float(x),
                float(y),
                float(z),
                float(intensity[index]),
            )

        excess = len(self.voxels) - self.max_points
        for _ in range(max(0, excess)):
            self.voxels.pop(next(iter(self.voxels)))

    def publish_map(self):
        if not self.voxels:
            return
        values = self.voxel_values()
        msg = PointCloud2()
        msg.header.frame_id = self.target_frame
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.height = 1
        msg.width = values.shape[0]
        msg.fields = [
            PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
            PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
            PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
            PointField(name="intensity", offset=12, datatype=PointField.FLOAT32, count=1),
        ]
        msg.is_bigendian = False
        msg.point_step = 16
        msg.row_step = msg.point_step * msg.width
        msg.is_dense = False
        msg.data = values.tobytes()
        self.publisher.publish(msg)

    def report_stats(self):
        self.get_logger().info(
            f"visual cloud stats: received={self.received}, integrated={self.integrated}, "
            f"skipped_rate={self.skipped_rate}, skipped_tf={self.skipped_tf}, "
            f"voxels={len(self.voxels)}"
        )

    def handle_save_request(self, request, response):
        del request
        try:
            paths = self.save_map()
        except RuntimeError as exc:
            response.success = False
            response.message = str(exc)
            return response
        except OSError as exc:
            response.success = False
            response.message = f"failed to save map: {exc}"
            return response

        response.success = True
        response.message = "saved " + ", ".join(str(path) for path in paths)
        return response

    def save_map(self, suffix=None):
        if np is None:
            raise RuntimeError("numpy is required for saving cloud maps")
        if not self.voxels:
            raise RuntimeError("no accumulated cloud points to save yet")

        values = self.voxel_values()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix_text = f"_{self.sanitize_filename(suffix)}" if suffix else ""
        stem = f"{self.map_name}_{stamp}{suffix_text}"

        self.save_dir.mkdir(parents=True, exist_ok=True)

        formats = self.save_formats()
        paths = []
        if "pcd" in formats:
            path = self.save_dir / f"{stem}.pcd"
            self.write_pcd_binary(path, values)
            paths.append(path)
        if "ply" in formats:
            path = self.save_dir / f"{stem}.ply"
            self.write_ply_ascii(path, values)
            paths.append(path)

        if not paths:
            raise RuntimeError(
                f"unsupported save_format '{self.save_format}', use pcd, ply, or both"
            )

        self.get_logger().info(
            f"saved accumulated cloud map with {values.shape[0]} points to "
            + ", ".join(str(path) for path in paths)
        )
        return paths

    def save_formats(self):
        if self.save_format in ("both", "pcd+ply", "ply+pcd"):
            return ("pcd", "ply")
        return (self.save_format,)

    def voxel_values(self):
        return np.asarray(list(self.voxels.values()), dtype="<f4")

    def write_pcd_binary(self, path, values):
        header = (
            "# .PCD v0.7 - Point Cloud Data file format\n"
            "VERSION 0.7\n"
            "FIELDS x y z intensity\n"
            "SIZE 4 4 4 4\n"
            "TYPE F F F F\n"
            "COUNT 1 1 1 1\n"
            f"WIDTH {values.shape[0]}\n"
            "HEIGHT 1\n"
            "VIEWPOINT 0 0 0 1 0 0 0\n"
            f"POINTS {values.shape[0]}\n"
            "DATA binary\n"
        )
        with path.open("wb") as stream:
            stream.write(header.encode("ascii"))
            stream.write(values.astype("<f4", copy=False).tobytes())

    def write_ply_ascii(self, path, values):
        with path.open("w", encoding="ascii") as stream:
            stream.write("ply\n")
            stream.write("format ascii 1.0\n")
            stream.write(f"element vertex {values.shape[0]}\n")
            stream.write("property float x\n")
            stream.write("property float y\n")
            stream.write("property float z\n")
            stream.write("property float intensity\n")
            stream.write("end_header\n")
            for x, y, z, intensity in values:
                stream.write(f"{x:.5f} {y:.5f} {z:.5f} {intensity:.5f}\n")

    def sanitize_filename(self, value):
        text = str(value).strip()
        safe = []
        for character in text:
            if character.isalnum() or character in ("-", "_", "."):
                safe.append(character)
            else:
                safe.append("_")
        return "".join(safe).strip("._") or "cloud_map"


def main(args=None):
    rclpy.init(args=args)
    node = Go2CloudAccumulator()
    try:
        rclpy.spin(node)
    except RuntimeError as exc:
        if "Unable to convert call argument" not in str(exc):
            raise
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node.save_on_shutdown:
            try:
                node.save_map("shutdown")
            except RuntimeError as exc:
                node.get_logger().warn(f"shutdown map save skipped: {exc}")
            except OSError as exc:
                node.get_logger().error(f"shutdown map save failed: {exc}")
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
