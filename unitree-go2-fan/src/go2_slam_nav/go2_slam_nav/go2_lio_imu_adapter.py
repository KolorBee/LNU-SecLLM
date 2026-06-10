import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


class Go2LioImuAdapter(Node):
    def __init__(self):
        super().__init__("go2_lio_imu_adapter")

        self.declare_parameter("input_topic", "/utlidar/imu")
        self.declare_parameter("output_topic", "/imu_lio")
        self.declare_parameter("frame_id", "utlidar_imu")
        self.declare_parameter("stamp_mode", "input")
        self.declare_parameter("monotonic_stamp_step_ns", 1000)
        self.declare_parameter("force_monotonic_output", True)
        self.declare_parameter("axis_mode", "identity")
        self.declare_parameter("replace_zero_covariance", True)
        self.declare_parameter("angular_velocity_scale", 1.0)
        self.declare_parameter("linear_acceleration_scale", 1.0)
        self.declare_parameter("orientation_variance", 0.05)
        self.declare_parameter("angular_velocity_variance", 0.02)
        self.declare_parameter("linear_acceleration_variance", 0.1)

        self.input_topic = self.get_parameter("input_topic").value
        self.output_topic = self.get_parameter("output_topic").value
        self.frame_id = self.get_parameter("frame_id").value
        self.stamp_mode = self.get_parameter("stamp_mode").value
        self.monotonic_stamp_step_ns = max(
            1, int(self.get_parameter("monotonic_stamp_step_ns").value)
        )
        self.force_monotonic_output = as_bool(
            self.get_parameter("force_monotonic_output").value
        )
        self.axis_mode = str(self.get_parameter("axis_mode").value).strip().lower()
        if self.axis_mode not in (
            "identity",
            "unitree_gyro_z_flip",
            "unitree_ned_to_ros",
        ):
            self.get_logger().warn(
                f"Unknown axis_mode={self.axis_mode!r}; falling back to identity"
            )
            self.axis_mode = "identity"
        self.replace_zero_covariance = as_bool(
            self.get_parameter("replace_zero_covariance").value
        )
        self.angular_velocity_scale = float(
            self.get_parameter("angular_velocity_scale").value
        )
        self.linear_acceleration_scale = float(
            self.get_parameter("linear_acceleration_scale").value
        )
        self.orientation_variance = float(
            self.get_parameter("orientation_variance").value
        )
        self.angular_velocity_variance = float(
            self.get_parameter("angular_velocity_variance").value
        )
        self.linear_acceleration_variance = float(
            self.get_parameter("linear_acceleration_variance").value
        )
        self.last_output_stamp_ns = None
        self.last_input_stamp_ns = None
        self.input_nonascending_stamps = 0
        self.corrected_nonascending_stamps = 0
        self.zero_stamp_replacements = 0
        self.bad_stamp_mode_reported = False

        self.received = 0
        self.published = 0
        qos = QoSProfile(depth=20, reliability=ReliabilityPolicy.BEST_EFFORT)
        pub_qos = QoSProfile(depth=20, reliability=ReliabilityPolicy.RELIABLE)
        self.publisher = self.create_publisher(Imu, self.output_topic, pub_qos)
        self.subscription = self.create_subscription(
            Imu,
            self.input_topic,
            self.imu_callback,
            qos,
        )
        self.timer = self.create_timer(5.0, self.report_stats)

        self.get_logger().info(
            f"LIO IMU adapter {self.input_topic} -> {self.output_topic}, "
            f"frame_id={self.frame_id}, stamp_mode={self.stamp_mode}, "
            f"monotonic_stamp_step_ns={self.monotonic_stamp_step_ns}, "
            f"force_monotonic_output={self.force_monotonic_output}, "
            f"axis_mode={self.axis_mode}, "
            f"replace_zero_covariance={self.replace_zero_covariance}, "
            f"angular_velocity_scale={self.angular_velocity_scale}, "
            f"linear_acceleration_scale={self.linear_acceleration_scale}"
        )

    def imu_callback(self, msg):
        self.received += 1
        now = self.get_clock().now()
        if self.frame_id:
            msg.header.frame_id = self.frame_id

        stamp_ns = self.selected_stamp_ns(msg, now.nanoseconds)
        if self.force_monotonic_output or self.stamp_mode == "monotonic_input":
            stamp_ns = self.monotonic_output_stamp_ns(stamp_ns)
        msg.header.stamp.sec = int(stamp_ns // 1_000_000_000)
        msg.header.stamp.nanosec = int(stamp_ns % 1_000_000_000)

        self.rotate_imu_axes(msg)
        self.scale_imu_units(msg)
        if self.replace_zero_covariance:
            self.replace_covariance_if_zero(msg)
        self.publisher.publish(msg)
        self.published += 1

    def selected_stamp_ns(self, msg, now_ns):
        stamp_ns = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec

        if self.last_input_stamp_ns is not None and stamp_ns <= self.last_input_stamp_ns:
            self.input_nonascending_stamps += 1
        self.last_input_stamp_ns = stamp_ns

        if stamp_ns <= 0:
            self.zero_stamp_replacements += 1
            stamp_ns = now_ns

        if self.stamp_mode == "now":
            return now_ns
        if self.stamp_mode in ("input", "monotonic_input"):
            return stamp_ns

        if not self.bad_stamp_mode_reported:
            self.get_logger().warn(
                f"Unknown stamp_mode '{self.stamp_mode}', keeping input timestamps."
            )
            self.bad_stamp_mode_reported = True
        return stamp_ns

    def monotonic_output_stamp_ns(self, stamp_ns):
        # FAST-LIO compares timestamps as double seconds in a few places. Keeping
        # a microsecond-scale or larger spacing prevents adjacent epoch stamps
        # from collapsing to the same floating-point value.
        if (
            self.last_output_stamp_ns is not None
            and stamp_ns <= self.last_output_stamp_ns + self.monotonic_stamp_step_ns
        ):
            stamp_ns = self.last_output_stamp_ns + self.monotonic_stamp_step_ns
            self.corrected_nonascending_stamps += 1
        self.last_output_stamp_ns = stamp_ns
        return stamp_ns

    def rotate_imu_axes(self, msg):
        if self.axis_mode == "unitree_gyro_z_flip":
            msg.angular_velocity.z *= -1.0
            return

        if self.axis_mode != "unitree_ned_to_ros":
            return

        # Observed on /utlidar/imu: yaw-rate sign is opposite to Go2 odom yaw,
        # and stationary acceleration is near -9.8 on Z. Treat it as a
        # body/NED-like convention and rotate vectors 180 deg about X:
        # x forward unchanged, y right -> left, z down -> up.
        msg.angular_velocity.y *= -1.0
        msg.angular_velocity.z *= -1.0
        msg.linear_acceleration.y *= -1.0
        msg.linear_acceleration.z *= -1.0

    def scale_imu_units(self, msg):
        if self.angular_velocity_scale != 1.0:
            msg.angular_velocity.x *= self.angular_velocity_scale
            msg.angular_velocity.y *= self.angular_velocity_scale
            msg.angular_velocity.z *= self.angular_velocity_scale
        if self.linear_acceleration_scale != 1.0:
            msg.linear_acceleration.x *= self.linear_acceleration_scale
            msg.linear_acceleration.y *= self.linear_acceleration_scale
            msg.linear_acceleration.z *= self.linear_acceleration_scale

    def replace_covariance_if_zero(self, msg):
        if all(value == 0.0 for value in msg.orientation_covariance):
            msg.orientation_covariance[0] = self.orientation_variance
            msg.orientation_covariance[4] = self.orientation_variance
            msg.orientation_covariance[8] = self.orientation_variance
        if all(value == 0.0 for value in msg.angular_velocity_covariance):
            msg.angular_velocity_covariance[0] = self.angular_velocity_variance
            msg.angular_velocity_covariance[4] = self.angular_velocity_variance
            msg.angular_velocity_covariance[8] = self.angular_velocity_variance
        if all(value == 0.0 for value in msg.linear_acceleration_covariance):
            msg.linear_acceleration_covariance[0] = self.linear_acceleration_variance
            msg.linear_acceleration_covariance[4] = self.linear_acceleration_variance
            msg.linear_acceleration_covariance[8] = self.linear_acceleration_variance

    def report_stats(self):
        if self.received == 0:
            return
        self.get_logger().info(
            f"LIO IMU adapter stats: received={self.received}, "
            f"published={self.published}, "
            f"input_nonascending_stamps={self.input_nonascending_stamps}, "
            f"corrected_output_stamps={self.corrected_nonascending_stamps}, "
            f"zero_stamp_replacements={self.zero_stamp_replacements}"
        )


def main(args=None):
    rclpy.init(args=args)
    node = Go2LioImuAdapter()
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
