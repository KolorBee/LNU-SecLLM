import math
import struct

try:
    import numpy as np
except ImportError:
    np = None

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile
from sensor_msgs.msg import PointCloud2, PointField


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


class Go2CloudThrottle(Node):
    def __init__(self):
        super().__init__("go2_cloud_throttle")

        self.declare_parameter("input_topic", "/lidar_points")
        self.declare_parameter("output_topic", "/lidar_points_slam")
        self.declare_parameter("max_rate", 2.0)
        self.declare_parameter("stamp_mode", "now")
        self.declare_parameter("point_stride", 1)
        self.declare_parameter("filter_enabled", False)
        self.declare_parameter("min_x", -1000.0)
        self.declare_parameter("max_x", 1000.0)
        self.declare_parameter("min_y", -1000.0)
        self.declare_parameter("max_y", 1000.0)
        self.declare_parameter("min_z", -1000.0)
        self.declare_parameter("max_z", 1000.0)
        self.declare_parameter("min_range", 0.0)
        self.declare_parameter("max_range", 0.0)
        self.declare_parameter("self_filter_enabled", False)
        self.declare_parameter("self_min_x", -0.65)
        self.declare_parameter("self_max_x", 0.55)
        self.declare_parameter("self_min_y", -0.45)
        self.declare_parameter("self_max_y", 0.45)
        self.declare_parameter("self_min_z", -0.50)
        self.declare_parameter("self_max_z", 0.75)
        self.declare_parameter("require_subscriber", False)

        self.input_topic = self.get_parameter("input_topic").value
        self.output_topic = self.get_parameter("output_topic").value
        self.max_rate = float(self.get_parameter("max_rate").value)
        self.stamp_mode = self.get_parameter("stamp_mode").value
        self.point_stride = max(1, int(self.get_parameter("point_stride").value))
        self.filter_enabled = as_bool(self.get_parameter("filter_enabled").value)
        self.min_x = float(self.get_parameter("min_x").value)
        self.max_x = float(self.get_parameter("max_x").value)
        self.min_y = float(self.get_parameter("min_y").value)
        self.max_y = float(self.get_parameter("max_y").value)
        self.min_z = float(self.get_parameter("min_z").value)
        self.max_z = float(self.get_parameter("max_z").value)
        self.min_range = max(0.0, float(self.get_parameter("min_range").value))
        self.max_range = max(0.0, float(self.get_parameter("max_range").value))
        self.self_filter_enabled = as_bool(
            self.get_parameter("self_filter_enabled").value
        )
        self.self_min_x = float(self.get_parameter("self_min_x").value)
        self.self_max_x = float(self.get_parameter("self_max_x").value)
        self.self_min_y = float(self.get_parameter("self_min_y").value)
        self.self_max_y = float(self.get_parameter("self_max_y").value)
        self.self_min_z = float(self.get_parameter("self_min_z").value)
        self.self_max_z = float(self.get_parameter("self_max_z").value)
        self.require_subscriber = as_bool(
            self.get_parameter("require_subscriber").value
        )
        self.min_period_ns = int(1e9 / self.max_rate) if self.max_rate > 0.0 else 0
        self.last_pub_ns = None
        self.received = 0
        self.published = 0
        self.dropped = 0
        self.no_subscriber_skipped = 0
        self.bad_stamp_mode_reported = False
        self.bad_fields_reported = False
        self.vectorized_filter_failed_reported = False
        self.decimate_offset = 0

        sub_qos = QoSProfile(depth=1)
        pub_qos = QoSProfile(depth=3)

        self.publisher = self.create_publisher(PointCloud2, self.output_topic, pub_qos)
        self.subscription = self.create_subscription(
            PointCloud2,
            self.input_topic,
            self.cloud_callback,
            sub_qos,
        )
        self.timer = self.create_timer(5.0, self.report_stats)
        self.get_logger().info(
            f"Throttling {self.input_topic} -> {self.output_topic} at "
            f"{self.max_rate:.2f} Hz, stamp_mode={self.stamp_mode}, "
            f"point_stride={self.point_stride}, filter={self.filter_enabled}, "
            f"self_filter={self.self_filter_enabled}, "
            f"require_subscriber={self.require_subscriber}"
        )

    def cloud_callback(self, msg):
        self.received += 1

        if self.require_subscriber and self.publisher.get_subscription_count() == 0:
            self.no_subscriber_skipped += 1
            return

        now = self.get_clock().now()
        now_ns = now.nanoseconds

        if self.last_pub_ns is not None and self.min_period_ns > 0:
            if now_ns - self.last_pub_ns < self.min_period_ns:
                self.dropped += 1
                return

        if self.stamp_mode == "now":
            msg.header.stamp = now.to_msg()
        elif self.stamp_mode != "input" and not self.bad_stamp_mode_reported:
            self.get_logger().warn(
                f"Unknown stamp_mode '{self.stamp_mode}', keeping input timestamps."
            )
            self.bad_stamp_mode_reported = True

        if self.point_stride > 1 or self.filter_enabled or self.self_filter_enabled:
            msg = self.filter_cloud(msg)
            self.decimate_offset = (self.decimate_offset + 1) % self.point_stride

        self.publisher.publish(msg)
        self.last_pub_ns = now_ns
        self.published += 1

    def report_stats(self):
        if self.received == 0:
            return
        self.get_logger().info(
            f"cloud throttle stats: received={self.received}, "
            f"published={self.published}, dropped={self.dropped}, "
            f"no_subscriber_skipped={self.no_subscriber_skipped}"
        )

    def filter_cloud(self, msg):
        point_count = msg.width * msg.height
        if point_count <= 1:
            return msg

        offsets = self.xyz_offsets(msg)
        if offsets is None:
            if not self.bad_fields_reported:
                self.get_logger().warn(
                    "PointCloud2 has no float32 x/y/z fields; falling back to stride only."
                )
                self.bad_fields_reported = True
            return self.decimate_cloud(msg)

        if np is not None:
            try:
                return self.filter_cloud_numpy(msg, point_count, offsets)
            except Exception as exc:
                if not self.vectorized_filter_failed_reported:
                    self.get_logger().warn(
                        f"Vectorized PointCloud2 filtering failed ({exc}); "
                        "falling back to Python filtering."
                    )
                    self.vectorized_filter_failed_reported = True

        start = self.decimate_offset if self.decimate_offset < point_count else 0
        endian = ">" if msg.is_bigendian else "<"
        unpack_float = struct.Struct(endian + "f").unpack_from
        x_offset, y_offset, z_offset = offsets
        min_range_sq = self.min_range * self.min_range
        max_range_sq = self.max_range * self.max_range if self.max_range > 0.0 else 0.0
        out = PointCloud2()
        out.header = msg.header
        out.fields = msg.fields
        out.is_bigendian = msg.is_bigendian
        out.point_step = msg.point_step
        out.is_dense = msg.is_dense
        out.height = 1

        src = msg.data
        src_step = msg.point_step
        out_data = bytearray()
        for src_index in range(start, point_count, self.point_stride):
            src_offset = src_index * src_step
            x = unpack_float(src, src_offset + x_offset)[0]
            y = unpack_float(src, src_offset + y_offset)[0]
            z = unpack_float(src, src_offset + z_offset)[0]
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                continue
            if not self.keep_point(x, y, z, min_range_sq, max_range_sq):
                continue
            out_data.extend(src[src_offset:src_offset + src_step])

        out.width = len(out_data) // out.point_step
        out.row_step = out.width * out.point_step
        out.data = out_data

        return out

    def filter_cloud_numpy(self, msg, point_count, offsets):
        start = self.decimate_offset if self.decimate_offset < point_count else 0
        endian = ">" if msg.is_bigendian else "<"
        xyz_dtype = np.dtype({
            "names": ("x", "y", "z"),
            "formats": (endian + "f4", endian + "f4", endian + "f4"),
            "offsets": offsets,
            "itemsize": msg.point_step,
        })
        record_dtype = np.dtype((np.void, msg.point_step))

        cloud = np.frombuffer(msg.data, dtype=xyz_dtype, count=point_count)
        indices = np.arange(start, point_count, self.point_stride, dtype=np.int64)
        if indices.size == 0:
            return self.empty_cloud_like(msg)

        x = cloud["x"][indices]
        y = cloud["y"][indices]
        z = cloud["z"][indices]
        mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
        mask &= (x >= self.min_x) & (x <= self.max_x)
        mask &= (y >= self.min_y) & (y <= self.max_y)
        mask &= (z >= self.min_z) & (z <= self.max_z)

        range_sq = x * x + y * y + z * z
        if self.min_range > 0.0:
            mask &= range_sq >= self.min_range * self.min_range
        if self.max_range > 0.0:
            mask &= range_sq <= self.max_range * self.max_range

        if self.self_filter_enabled:
            in_self_box = (
                (x >= self.self_min_x) & (x <= self.self_max_x)
                & (y >= self.self_min_y) & (y <= self.self_max_y)
                & (z >= self.self_min_z) & (z <= self.self_max_z)
            )
            mask &= ~in_self_box

        selected = indices[mask]
        if selected.size == 0:
            return self.empty_cloud_like(msg)

        records = np.frombuffer(msg.data, dtype=record_dtype, count=point_count)
        return self.cloud_from_bytes(msg, records[selected].tobytes(), selected.size)

    def decimate_cloud(self, msg):
        point_count = msg.width * msg.height
        if point_count <= 1:
            return msg

        if np is not None:
            try:
                start = self.decimate_offset if self.decimate_offset < point_count else 0
                record_dtype = np.dtype((np.void, msg.point_step))
                records = np.frombuffer(msg.data, dtype=record_dtype, count=point_count)
                selected = records[start::self.point_stride]
                return self.cloud_from_bytes(msg, selected.tobytes(), selected.size)
            except Exception as exc:
                if not self.vectorized_filter_failed_reported:
                    self.get_logger().warn(
                        f"Vectorized PointCloud2 decimation failed ({exc}); "
                        "falling back to Python decimation."
                    )
                    self.vectorized_filter_failed_reported = True

        start = self.decimate_offset if self.decimate_offset < point_count else 0
        output_points = (point_count - start + self.point_stride - 1) // self.point_stride
        if output_points <= 0:
            return self.empty_cloud_like(msg)

        out_data = bytearray(output_points * msg.point_step)

        src = msg.data
        dst_offset = 0
        for src_index in range(start, point_count, self.point_stride):
            src_offset = src_index * msg.point_step
            out_data[dst_offset:dst_offset + msg.point_step] = (
                src[src_offset:src_offset + msg.point_step]
            )
            dst_offset += msg.point_step

        return self.cloud_from_bytes(msg, out_data, output_points)

    def empty_cloud_like(self, msg):
        return self.cloud_from_bytes(msg, b"", 0)

    def cloud_from_bytes(self, msg, data, point_count):
        out = PointCloud2()
        out.header = msg.header
        out.fields = msg.fields
        out.is_bigendian = msg.is_bigendian
        out.point_step = msg.point_step
        out.is_dense = msg.is_dense
        out.height = 1
        out.width = int(point_count)
        out.row_step = out.width * out.point_step
        out.data = data
        return out

    def keep_point(self, x, y, z, min_range_sq, max_range_sq):
        if x < self.min_x or x > self.max_x:
            return False
        if y < self.min_y or y > self.max_y:
            return False
        if z < self.min_z or z > self.max_z:
            return False

        range_sq = x * x + y * y + z * z
        if min_range_sq > 0.0 and range_sq < min_range_sq:
            return False
        if max_range_sq > 0.0 and range_sq > max_range_sq:
            return False

        if self.self_filter_enabled:
            in_self_box = (
                self.self_min_x <= x <= self.self_max_x
                and self.self_min_y <= y <= self.self_max_y
                and self.self_min_z <= z <= self.self_max_z
            )
            if in_self_box:
                return False

        return True

    def xyz_offsets(self, msg):
        offsets = {}
        for field in msg.fields:
            if field.name in ("x", "y", "z"):
                if field.datatype != PointField.FLOAT32 or field.count != 1:
                    return None
                offsets[field.name] = field.offset
        if not all(name in offsets for name in ("x", "y", "z")):
            return None
        return offsets["x"], offsets["y"], offsets["z"]


def main(args=None):
    rclpy.init(args=args)
    node = Go2CloudThrottle()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except RuntimeError as exc:
        if "Unable to convert call argument to Python object" not in str(exc):
            raise
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
