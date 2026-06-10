import math

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import JointState


JOINT_NAMES = [
    "FL_hip_joint",
    "FL_thigh_joint",
    "FL_calf_joint",
    "FR_hip_joint",
    "FR_thigh_joint",
    "FR_calf_joint",
    "RL_hip_joint",
    "RL_thigh_joint",
    "RL_calf_joint",
    "RR_hip_joint",
    "RR_thigh_joint",
    "RR_calf_joint",
]

# Unitree/go2_ros2_sdk motor order: FR, FL, RR, RL, each hip/thigh/calf.
GO2_SDK_MOTOR_INDEX = [3, 4, 5, 0, 1, 2, 9, 10, 11, 6, 7, 8]


def load_low_state_type(preferred_package):
    candidates = []
    if preferred_package != "auto":
        candidates.append(preferred_package)
    candidates.extend(["unitree_go", "go2_interfaces"])

    errors = []
    for package in dict.fromkeys(candidates):
        try:
            if package == "unitree_go":
                from unitree_go.msg import LowState  # type: ignore

                return LowState, package
            if package == "go2_interfaces":
                from go2_interfaces.msg import LowState  # type: ignore

                return LowState, package
        except ImportError as exc:
            errors.append(f"{package}: {exc}")

    raise RuntimeError(
        "Cannot import a supported LowState message type. Source "
        "/home/star/unitree_ros2/setup_go2.sh for unitree_go/msg/LowState or "
        "/home/star/go2_ros2_sdk/install/setup.bash for go2_interfaces/msg/LowState. "
        "Import errors: " + "; ".join(errors)
    )


class Go2LowStateJointRelay(Node):
    def __init__(self):
        super().__init__("go2_lowstate_joint_relay")
        self.declare_parameter("lowstate_topic", "/lowstate")
        self.declare_parameter("output_topic", "/joint_states")
        self.declare_parameter("message_package", "auto")
        self.declare_parameter("max_rate", 50.0)
        self.declare_parameter("publish_velocity", True)
        self.declare_parameter("publish_effort", True)

        self.lowstate_topic = str(self.get_parameter("lowstate_topic").value)
        self.output_topic = str(self.get_parameter("output_topic").value)
        self.message_package = str(self.get_parameter("message_package").value)
        self.max_rate = max(0.0, float(self.get_parameter("max_rate").value))
        self.publish_velocity = bool(self.get_parameter("publish_velocity").value)
        self.publish_effort = bool(self.get_parameter("publish_effort").value)
        self.min_period_ns = int(1e9 / self.max_rate) if self.max_rate > 0 else 0
        self.last_publish_ns = 0
        self.received = 0
        self.published = 0

        low_state_type, loaded_package = load_low_state_type(self.message_package)
        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self.publisher = self.create_publisher(JointState, self.output_topic, 10)
        self.subscription = self.create_subscription(
            low_state_type, self.lowstate_topic, self.on_low_state, qos
        )
        self.stats_timer = self.create_timer(10.0, self.log_stats)
        self.get_logger().info(
            f"relaying {self.lowstate_topic} -> {self.output_topic}, "
            f"type={loaded_package}/msg/LowState, max_rate={self.max_rate} Hz"
        )

    def on_low_state(self, msg):
        self.received += 1
        now = self.get_clock().now()
        now_ns = now.nanoseconds
        if self.min_period_ns and now_ns - self.last_publish_ns < self.min_period_ns:
            return

        motor_state = list(getattr(msg, "motor_state", []))
        if len(motor_state) <= max(GO2_SDK_MOTOR_INDEX):
            self.get_logger().warn(
                f"lowstate motor_state has {len(motor_state)} entries, need at least 12",
                throttle_duration_sec=5.0,
            )
            return

        joint_state = JointState()
        joint_state.header.stamp = now.to_msg()
        joint_state.name = JOINT_NAMES
        joint_state.position = [
            self.clean_float(getattr(motor_state[i], "q", 0.0))
            for i in GO2_SDK_MOTOR_INDEX
        ]
        if self.publish_velocity:
            joint_state.velocity = [
                self.clean_float(getattr(motor_state[i], "dq", 0.0))
                for i in GO2_SDK_MOTOR_INDEX
            ]
        if self.publish_effort:
            joint_state.effort = [
                self.clean_float(getattr(motor_state[i], "tau_est", 0.0))
                for i in GO2_SDK_MOTOR_INDEX
            ]

        self.publisher.publish(joint_state)
        self.last_publish_ns = now_ns
        self.published += 1

    @staticmethod
    def clean_float(value):
        value = float(value)
        return value if math.isfinite(value) else 0.0

    def log_stats(self):
        self.get_logger().info(
            f"lowstate joint relay stats: received={self.received}, "
            f"published={self.published}"
        )


def main(args=None):
    rclpy.init(args=args)
    try:
        node = Go2LowStateJointRelay()
    except RuntimeError as exc:
        print(str(exc))
        if rclpy.ok():
            rclpy.shutdown()
        return

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
