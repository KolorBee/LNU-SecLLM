from copy import deepcopy

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from tf2_ros import TransformBroadcaster
from math import atan2, sin, cos


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


def yaw_from_quaternion(q):
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return atan2(siny_cosp, cosy_cosp)


def set_yaw_only(q, yaw):
    q.x = 0.0
    q.y = 0.0
    q.z = sin(yaw * 0.5)
    q.w = cos(yaw * 0.5)


class Go2OdomRelay(Node):
    def __init__(self):
        super().__init__("go2_odom_relay")

        self.declare_parameter("input_topic", "/utlidar/robot_odom")
        self.declare_parameter("output_topic", "/odom")
        self.declare_parameter("odom_frame_id", "odom")
        self.declare_parameter("base_frame_id", "base_link")
        self.declare_parameter("publish_tf", True)
        self.declare_parameter("max_rate", 30.0)
        self.declare_parameter("stamp_mode", "now")
        self.declare_parameter("flatten_to_2d", True)
        self.declare_parameter("replace_zero_covariance", False)
        self.declare_parameter("pose_xy_variance", 0.05)
        self.declare_parameter("pose_z_variance", 1000.0)
        self.declare_parameter("pose_rp_variance", 1000.0)
        self.declare_parameter("pose_yaw_variance", 0.03)
        self.declare_parameter("twist_xy_variance", 0.05)
        self.declare_parameter("twist_z_variance", 1000.0)
        self.declare_parameter("twist_rp_variance", 1000.0)
        self.declare_parameter("twist_yaw_variance", 0.05)

        self.input_topic = self.get_parameter("input_topic").value
        self.output_topic = self.get_parameter("output_topic").value
        self.odom_frame_id = self.get_parameter("odom_frame_id").value
        self.base_frame_id = self.get_parameter("base_frame_id").value
        self.publish_tf = as_bool(self.get_parameter("publish_tf").value)
        self.max_rate = float(self.get_parameter("max_rate").value)
        self.stamp_mode = self.get_parameter("stamp_mode").value
        self.flatten_to_2d = as_bool(self.get_parameter("flatten_to_2d").value)
        self.replace_zero_covariance = as_bool(
            self.get_parameter("replace_zero_covariance").value
        )
        self.pose_xy_variance = float(self.get_parameter("pose_xy_variance").value)
        self.pose_z_variance = float(self.get_parameter("pose_z_variance").value)
        self.pose_rp_variance = float(self.get_parameter("pose_rp_variance").value)
        self.pose_yaw_variance = float(self.get_parameter("pose_yaw_variance").value)
        self.twist_xy_variance = float(self.get_parameter("twist_xy_variance").value)
        self.twist_z_variance = float(self.get_parameter("twist_z_variance").value)
        self.twist_rp_variance = float(self.get_parameter("twist_rp_variance").value)
        self.twist_yaw_variance = float(self.get_parameter("twist_yaw_variance").value)
        self.min_period_ns = int(1e9 / self.max_rate) if self.max_rate > 0.0 else 0
        self.last_pub_ns = None
        self.latest_msg = None
        self.latest_seq = 0
        self.last_published_seq = 0
        self.received = 0
        self.published = 0
        self.bad_stamp_mode_reported = False

        sub_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        pub_qos = QoSProfile(depth=10)
        self.publisher = self.create_publisher(Odometry, self.output_topic, pub_qos)
        self.subscription = self.create_subscription(
            Odometry,
            self.input_topic,
            self.odom_callback,
            sub_qos,
        )
        self.tf_broadcaster = TransformBroadcaster(self) if self.publish_tf else None
        self.publish_timer = None
        if self.max_rate > 0.0:
            self.publish_timer = self.create_timer(1.0 / self.max_rate, self.publish_latest)
        self.timer = self.create_timer(5.0, self.report_stats)

        self.get_logger().info(
            f"Relaying odometry {self.input_topic} -> {self.output_topic} at "
            f"{self.max_rate:.1f} Hz, tf={self.publish_tf}, "
            f"frames={self.odom_frame_id}->{self.base_frame_id}, "
            f"stamp_mode={self.stamp_mode}, flatten_to_2d={self.flatten_to_2d}, "
            f"replace_zero_covariance={self.replace_zero_covariance}"
        )

    def odom_callback(self, msg):
        self.received += 1
        if self.publish_timer is not None:
            self.latest_msg = msg
            self.latest_seq += 1
            return

        self.process_and_publish(msg)

    def publish_latest(self):
        if self.latest_msg is None or self.latest_seq == self.last_published_seq:
            return
        msg = deepcopy(self.latest_msg)
        self.process_and_publish(msg)
        self.last_published_seq = self.latest_seq

    def process_and_publish(self, msg):
        now = self.get_clock().now()
        now_ns = now.nanoseconds
        if self.last_pub_ns is not None and self.min_period_ns > 0:
            if now_ns - self.last_pub_ns < self.min_period_ns:
                return

        if self.stamp_mode == "now":
            msg.header.stamp = now.to_msg()
        elif self.stamp_mode != "input" and not self.bad_stamp_mode_reported:
            self.get_logger().warn(
                f"Unknown stamp_mode '{self.stamp_mode}', keeping input timestamps."
            )
            self.bad_stamp_mode_reported = True

        msg.header.frame_id = self.odom_frame_id
        msg.child_frame_id = self.base_frame_id

        if self.flatten_to_2d:
            msg.pose.pose.position.z = 0.0
            set_yaw_only(
                msg.pose.pose.orientation,
                yaw_from_quaternion(msg.pose.pose.orientation),
            )
            msg.twist.twist.linear.z = 0.0
            msg.twist.twist.angular.x = 0.0
            msg.twist.twist.angular.y = 0.0

        if self.replace_zero_covariance:
            self.replace_covariance_if_zero(msg)

        self.publisher.publish(msg)

        if self.tf_broadcaster is not None:
            transform = TransformStamped()
            transform.header = msg.header
            transform.child_frame_id = msg.child_frame_id
            transform.transform.translation.x = msg.pose.pose.position.x
            transform.transform.translation.y = msg.pose.pose.position.y
            transform.transform.translation.z = msg.pose.pose.position.z
            transform.transform.rotation = msg.pose.pose.orientation
            self.tf_broadcaster.sendTransform(transform)

        self.last_pub_ns = now_ns
        self.published += 1

    def report_stats(self):
        if self.received == 0:
            return
        self.get_logger().info(
            f"odom relay stats: received={self.received}, published={self.published}"
        )

    def replace_covariance_if_zero(self, msg):
        if all(value == 0.0 for value in msg.pose.covariance):
            msg.pose.covariance[0] = self.pose_xy_variance
            msg.pose.covariance[7] = self.pose_xy_variance
            msg.pose.covariance[14] = self.pose_z_variance
            msg.pose.covariance[21] = self.pose_rp_variance
            msg.pose.covariance[28] = self.pose_rp_variance
            msg.pose.covariance[35] = self.pose_yaw_variance

        if all(value == 0.0 for value in msg.twist.covariance):
            msg.twist.covariance[0] = self.twist_xy_variance
            msg.twist.covariance[7] = self.twist_xy_variance
            msg.twist.covariance[14] = self.twist_z_variance
            msg.twist.covariance[21] = self.twist_rp_variance
            msg.twist.covariance[28] = self.twist_rp_variance
            msg.twist.covariance[35] = self.twist_yaw_variance


def main(args=None):
    rclpy.init(args=args)
    node = Go2OdomRelay()
    try:
        rclpy.spin(node)
    except RuntimeError as exc:
        if "Unable to convert call argument" not in str(exc):
            raise
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
