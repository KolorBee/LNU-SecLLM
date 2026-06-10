import math

try:
    import numpy as np
except ImportError:
    np = None

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import PointCloud2, PointField


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


class Go2LioPointsAdapter(Node):
    def __init__(self):
        super().__init__("go2_lio_points_adapter")

        self.declare_parameter("input_topic", "/lidar_points")
        self.declare_parameter("output_topic", "/points_raw")
        self.declare_parameter("output_frame_id", "")
        self.declare_parameter("axis_mode", "identity")
        self.declare_parameter("max_rate", 10.0)
        self.declare_parameter("point_stride", 1)
        self.declare_parameter("scan_period", 0.1)
        self.declare_parameter("stamp_mode", "input")
        self.declare_parameter("use_input_time_field", True)
        self.declare_parameter("add_time_fields", True)
        self.declare_parameter("add_ring_field", True)
        self.declare_parameter("infer_ring_from_vertical_angle", True)
        self.declare_parameter("ring_count", 128)
        self.declare_parameter("min_vertical_angle_deg", -25.0)
        self.declare_parameter("max_vertical_angle_deg", 15.0)
        self.declare_parameter("filter_enabled", True)
        self.declare_parameter("min_z", -2.0)
        self.declare_parameter("max_z", 3.0)
        self.declare_parameter("min_range", 0.2)
        self.declare_parameter("max_range", 80.0)

        self.input_topic = self.get_parameter("input_topic").value
        self.output_topic = self.get_parameter("output_topic").value
        self.output_frame_id = self.get_parameter("output_frame_id").value
        self.axis_mode = str(self.get_parameter("axis_mode").value).strip().lower()
        if self.axis_mode not in ("identity", "hesai_y_forward_to_ros"):
            self.get_logger().warn(
                f"Unknown axis_mode={self.axis_mode!r}; falling back to identity"
            )
            self.axis_mode = "identity"
        self.max_rate = float(self.get_parameter("max_rate").value)
        self.point_stride = max(1, int(self.get_parameter("point_stride").value))
        self.scan_period = max(0.001, float(self.get_parameter("scan_period").value))
        self.stamp_mode = self.get_parameter("stamp_mode").value
        self.use_input_time_field = as_bool(self.get_parameter("use_input_time_field").value)
        self.add_time_fields = as_bool(self.get_parameter("add_time_fields").value)
        self.add_ring_field = as_bool(self.get_parameter("add_ring_field").value)
        self.infer_ring = as_bool(
            self.get_parameter("infer_ring_from_vertical_angle").value
        )
        self.ring_count = max(1, int(self.get_parameter("ring_count").value))
        self.min_vertical_angle = math.radians(
            float(self.get_parameter("min_vertical_angle_deg").value)
        )
        self.max_vertical_angle = math.radians(
            float(self.get_parameter("max_vertical_angle_deg").value)
        )
        self.filter_enabled = as_bool(self.get_parameter("filter_enabled").value)
        self.min_z = float(self.get_parameter("min_z").value)
        self.max_z = float(self.get_parameter("max_z").value)
        self.min_range = max(0.0, float(self.get_parameter("min_range").value))
        self.max_range = max(0.0, float(self.get_parameter("max_range").value))

        self.min_period_ns = int(1e9 / self.max_rate) if self.max_rate > 0.0 else 0
        self.last_pub_ns = None
        self.decimate_offset = 0
        self.received = 0
        self.published = 0
        self.dropped_rate = 0
        self.bad_fields_reported = False
        self.no_numpy_reported = False

        sub_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)
        pub_qos = QoSProfile(depth=3, reliability=ReliabilityPolicy.RELIABLE)
        self.publisher = self.create_publisher(PointCloud2, self.output_topic, pub_qos)
        self.subscription = self.create_subscription(
            PointCloud2,
            self.input_topic,
            self.cloud_callback,
            sub_qos,
        )
        self.timer = self.create_timer(5.0, self.report_stats)

        self.get_logger().info(
            f"LIO point adapter {self.input_topic} -> {self.output_topic}, "
            f"axis_mode={self.axis_mode}, max_rate={self.max_rate:.2f} Hz, "
            f"stride={self.point_stride}, "
            f"scan_period={self.scan_period:.3f}s, add_time={self.add_time_fields}, "
            f"use_input_time={self.use_input_time_field}, "
            f"add_ring={self.add_ring_field}, infer_ring={self.infer_ring}"
        )

    def cloud_callback(self, msg):
        self.received += 1
        if np is None:
            if not self.no_numpy_reported:
                self.get_logger().error("numpy is required for go2_lio_points_adapter")
                self.no_numpy_reported = True
            return

        callback_now = self.get_clock().now()
        now_ns = callback_now.nanoseconds
        if self.last_pub_ns is not None and self.min_period_ns > 0:
            if now_ns - self.last_pub_ns < self.min_period_ns:
                self.dropped_rate += 1
                return

        fields = self.field_offsets(msg)
        if not {"x", "y", "z"}.issubset(fields):
            if not self.bad_fields_reported:
                self.get_logger().warn(
                    "PointCloud2 has no float32 x/y/z fields; cannot adapt for LIO."
                )
                self.bad_fields_reported = True
            return

        out = self.adapt_cloud(msg, fields)
        if self.stamp_mode == "now":
            out.header.stamp = self.get_clock().now().to_msg()
        elif self.stamp_mode != "input":
            out.header.stamp = msg.header.stamp
        self.publisher.publish(out)
        self.last_pub_ns = now_ns
        self.published += 1
        self.decimate_offset = (self.decimate_offset + 1) % self.point_stride

    def field_offsets(self, msg):
        offsets = {}
        for field in msg.fields:
            offsets[field.name] = field
        return offsets

    def adapt_cloud(self, msg, fields):
        point_count = msg.width * msg.height
        start = self.decimate_offset if self.decimate_offset < point_count else 0
        indices = np.arange(start, point_count, self.point_stride, dtype=np.int64)
        endian = ">" if msg.is_bigendian else "<"

        dtype_names = ["x", "y", "z"]
        dtype_formats = [
            self.numpy_format(fields["x"], endian),
            self.numpy_format(fields["y"], endian),
            self.numpy_format(fields["z"], endian),
        ]
        dtype_offsets = [fields["x"].offset, fields["y"].offset, fields["z"].offset]

        intensity_field = self.find_field(fields, ("intensity", "reflectivity"))
        ring_field = self.find_field(fields, ("ring", "line", "laser_id"))
        time_field = None
        if self.use_input_time_field:
            time_field = self.find_field(fields, ("offset_time", "time", "timestamp"))

        if intensity_field is not None:
            dtype_names.append("intensity")
            dtype_formats.append(self.numpy_format(fields[intensity_field], endian))
            dtype_offsets.append(fields[intensity_field].offset)
        if ring_field is not None:
            dtype_names.append("ring")
            dtype_formats.append(self.numpy_format(fields[ring_field], endian))
            dtype_offsets.append(fields[ring_field].offset)
        if time_field is not None:
            dtype_names.append("time")
            dtype_formats.append(self.numpy_format(fields[time_field], endian))
            dtype_offsets.append(fields[time_field].offset)

        dtype = np.dtype({
            "names": dtype_names,
            "formats": dtype_formats,
            "offsets": dtype_offsets,
            "itemsize": msg.point_step,
        })
        cloud = np.frombuffer(msg.data, dtype=dtype, count=point_count)
        if indices.size == 0:
            return self.make_cloud(msg, np.empty((0, 7), dtype=np.float32))

        x = cloud["x"][indices]
        y = cloud["y"][indices]
        z = cloud["z"][indices]
        mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
        if self.filter_enabled:
            mask &= (z >= self.min_z) & (z <= self.max_z)
            range_sq = x * x + y * y + z * z
            if self.min_range > 0.0:
                mask &= range_sq >= self.min_range * self.min_range
            if self.max_range > 0.0:
                mask &= range_sq <= self.max_range * self.max_range

        selected = indices[mask]
        if selected.size == 0:
            return self.make_cloud(msg, np.empty((0, 7), dtype=np.float32))

        points = np.zeros((selected.size, 7), dtype=np.float32)
        self.copy_xyz_with_axis_mode(cloud, selected, points)

        if "intensity" in cloud.dtype.names:
            points[:, 3] = cloud["intensity"][selected]

        if "ring" in cloud.dtype.names:
            points[:, 4] = cloud["ring"][selected].astype(np.float32)
        elif self.add_ring_field and self.infer_ring:
            points[:, 4] = self.infer_rings(points[:, 0], points[:, 1], points[:, 2])

        if "time" in cloud.dtype.names:
            points[:, 5] = self.normalize_time(cloud["time"][selected])
        elif self.add_time_fields:
            points[:, 5] = np.linspace(
                0.0,
                self.scan_period,
                selected.size,
                endpoint=False,
                dtype=np.float32,
            )
        points[:, 6] = points[:, 5]
        return self.make_cloud(msg, points)

    def copy_xyz_with_axis_mode(self, cloud, selected, points):
        raw_x = cloud["x"][selected]
        raw_y = cloud["y"][selected]
        raw_z = cloud["z"][selected]

        if self.axis_mode == "hesai_y_forward_to_ros":
            # Hesai JT/Pandar decoding uses x=r*sin(azimuth), y=r*cos(azimuth),
            # so zero azimuth lies on +Y. Convert to ROS lidar axes:
            # +X forward, +Y left, +Z up.
            points[:, 0] = raw_y
            points[:, 1] = -raw_x
            points[:, 2] = raw_z
            return

        points[:, 0] = raw_x
        points[:, 1] = raw_y
        points[:, 2] = raw_z

    def find_field(self, fields, names):
        for name in names:
            if name in fields:
                return name
        return None

    def numpy_format(self, field, endian):
        formats = {
            PointField.INT8: "i1",
            PointField.UINT8: "u1",
            PointField.INT16: endian + "i2",
            PointField.UINT16: endian + "u2",
            PointField.INT32: endian + "i4",
            PointField.UINT32: endian + "u4",
            PointField.FLOAT32: endian + "f4",
            PointField.FLOAT64: endian + "f8",
        }
        return formats.get(field.datatype, endian + "f4")

    def infer_rings(self, x, y, z):
        horizontal = np.sqrt(x * x + y * y)
        angles = np.arctan2(z, horizontal)
        span = max(1e-6, self.max_vertical_angle - self.min_vertical_angle)
        rings = np.rint(
            (angles - self.min_vertical_angle) / span * (self.ring_count - 1)
        )
        return np.clip(rings, 0, self.ring_count - 1).astype(np.float32)

    def normalize_time(self, values):
        values = values.astype(np.float64, copy=False)
        if values.size == 0:
            return values.astype(np.float32)
        finite = np.isfinite(values)
        if not np.any(finite):
            return np.zeros(values.shape, dtype=np.float32)

        min_value = float(np.nanmin(values[finite]))
        max_value = float(np.nanmax(values[finite]))
        span = max(0.0, max_value - min_value)

        if max_value > max(self.scan_period * 2.0, 10.0):
            values = values - min_value
            if span > 1e7:
                values = values * 1e-9
            elif span > 1e4:
                values = values * 1e-6
            elif span > 10.0:
                values = values * 1e-3
        return np.clip(values, 0.0, self.scan_period).astype(np.float32)

    def make_cloud(self, src, points):
        msg = PointCloud2()
        msg.header = src.header
        if self.output_frame_id:
            msg.header.frame_id = self.output_frame_id
        msg.height = 1
        msg.width = points.shape[0]
        msg.fields = [
            PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
            PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
            PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
            PointField(name="intensity", offset=12, datatype=PointField.FLOAT32, count=1),
            PointField(name="ring", offset=16, datatype=PointField.UINT16, count=1),
            PointField(name="time", offset=20, datatype=PointField.FLOAT32, count=1),
            PointField(name="offset_time", offset=24, datatype=PointField.FLOAT32, count=1),
        ]
        msg.is_bigendian = False
        msg.point_step = 28
        msg.row_step = msg.point_step * msg.width
        msg.is_dense = False

        if points.shape[0] == 0:
            msg.data = b""
            return msg

        record = np.zeros(points.shape[0], dtype=[
            ("x", "<f4"),
            ("y", "<f4"),
            ("z", "<f4"),
            ("intensity", "<f4"),
            ("ring", "<u2"),
            ("padding", "<u2"),
            ("time", "<f4"),
            ("offset_time", "<f4"),
        ])
        record["x"] = points[:, 0]
        record["y"] = points[:, 1]
        record["z"] = points[:, 2]
        record["intensity"] = points[:, 3]
        record["ring"] = points[:, 4].astype(np.uint16)
        record["time"] = points[:, 5]
        record["offset_time"] = points[:, 6]
        msg.data = record.tobytes()
        return msg

    def report_stats(self):
        if self.received == 0:
            return
        self.get_logger().info(
            f"LIO point adapter stats: received={self.received}, "
            f"published={self.published}, dropped_rate={self.dropped_rate}"
        )


def main(args=None):
    rclpy.init(args=args)
    node = Go2LioPointsAdapter()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException, RuntimeError):
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
