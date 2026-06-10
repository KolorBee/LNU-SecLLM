import json
import math

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.logging import LoggingSeverity
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from geometry_msgs.msg import Twist
from std_srvs.srv import Empty
from unitree_api.msg import Request


ROBOT_SPORT_API_ID_BALANCESTAND = 1002
ROBOT_SPORT_API_ID_STOPMOVE = 1003
ROBOT_SPORT_API_ID_STANDUP = 1004
ROBOT_SPORT_API_ID_STANDDOWN = 1005
ROBOT_SPORT_API_ID_RECOVERYSTAND = 1006
ROBOT_SPORT_API_ID_MOVE = 1008
ROBOT_SPORT_API_ID_DAMP = 1001
ROBOT_SPORT_API_ID_DANCE1 = 1022
ROBOT_SPORT_API_ID_DANCE2 = 1023


class Go2CmdProcessor(Node):
    def __init__(self):
        super().__init__("go2_cmd_processor")

        # Declare parameters
        self.declare_parameter("rate", 20.0)
        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("request_topic", "/api/sport/request")
        self.declare_parameter("cmd_vel_timeout", 0.5)  # Timeout in seconds
        self.declare_parameter("log_level", "info")  # Logging level
        self.declare_parameter("max_vx", 0.15)
        self.declare_parameter("max_vy", 0.15)
        self.declare_parameter("max_wz", 0.6)
        self.declare_parameter("deadband", 0.01)
        self.declare_parameter("request_qos_reliability", "reliable")

        # Set the logger level based on the parameter
        log_level = self.get_parameter("log_level").value.lower()
        log_severity = {
            "debug": LoggingSeverity.DEBUG,
            "info": LoggingSeverity.INFO,
            "warn": LoggingSeverity.WARN,
            "error": LoggingSeverity.ERROR,
            "fatal": LoggingSeverity.FATAL,
        }.get(log_level, LoggingSeverity.INFO)
        self.get_logger().set_level(log_severity)

        self.rate = self.get_parameter("rate").value
        self.cmd_vel_topic = self.get_parameter("cmd_vel_topic").value
        self.request_topic = self.get_parameter("request_topic").value
        self.cmd_vel_timeout = self.get_parameter("cmd_vel_timeout").value
        self.max_vx = abs(float(self.get_parameter("max_vx").value))
        self.max_vy = abs(float(self.get_parameter("max_vy").value))
        self.max_wz = abs(float(self.get_parameter("max_wz").value))
        self.deadband = abs(float(self.get_parameter("deadband").value))
        request_qos_reliability = str(
            self.get_parameter("request_qos_reliability").value
        ).lower()
        if request_qos_reliability in ("best_effort", "besteffort", "best-effort"):
            request_reliability = QoSReliabilityPolicy.BEST_EFFORT
            request_reliability_name = "best_effort"
        else:
            request_reliability = QoSReliabilityPolicy.RELIABLE
            request_reliability_name = "reliable"

        # Time intervals
        self.publish_interval = 1.0 / self.rate
        self.cmd_vel_timeout_duration = self.cmd_vel_timeout
        self.last_cmd_time = None

        # Publishers
        qos = QoSProfile(
            reliability=request_reliability,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self.publisher = self.create_publisher(Request, self.request_topic, qos)

        # Subscribers
        self.subscription = self.create_subscription(
            Twist, self.cmd_vel_topic, self.cmd_vel_callback, 10
        )

        # Services
        self.create_service(Empty, "balance_stand", self.balance_stand_callback)
        self.create_service(Empty, "stop_move", self.stop_move_callback)
        self.create_service(Empty, "stand_up", self.stand_up_callback)
        self.create_service(Empty, "lay_down", self.lay_down_callback)
        self.create_service(Empty, "recover_stand", self.recover_stand_callback)
        self.create_service(Empty, "damping", self.damping_callback)
        self.create_service(Empty, "dance1", self.dance1_callback)
        self.create_service(Empty, "dance2", self.dance2_callback)

        # Timers
        self.timer = self.create_timer(self.publish_interval, self.timer_callback)
        self.stats_timer = self.create_timer(5.0, self.log_stats)

        # Command state
        self.current_request = None
        self.sent_idle_after_timeout = False
        self.reset_state = False
        self.cmd_count = 0
        self.request_count = 0
        self.last_cmd = (0.0, 0.0, 0.0)

        self.get_logger().info(
            "Go2 Command Processor Node Started: "
            f"{self.cmd_vel_topic} -> {self.request_topic}, "
            f"limits vx={self.max_vx}, vy={self.max_vy}, wz={self.max_wz}, "
            f"request_qos={request_reliability_name}"
        )

    def create_request(self, api_id, parameters=None):
        """Helper function to create a Request message."""
        req = Request()
        req.header.identity.api_id = int(api_id)
        if parameters is not None:
            req.parameter = parameters
        return req

    def cmd_vel_callback(self, msg: Twist):
        """
        Callback for cmd_vel messages. Converts the velocity commands into SportMode commands.
        """
        vx = self.clean_velocity(msg.linear.x, self.max_vx)
        vy = self.clean_velocity(msg.linear.y, self.max_vy)
        wz = self.clean_velocity(msg.angular.z, self.max_wz)
        self.last_cmd = (vx, vy, wz)
        self.cmd_count += 1
        self.last_cmd_time = self.get_clock().now()
        self.sent_idle_after_timeout = False

        if self.is_zero(vx) and self.is_zero(vy) and self.is_zero(wz):
            req = self.create_request(api_id=ROBOT_SPORT_API_ID_STOPMOVE)
            self.get_logger().debug("Received zero cmd_vel; publishing StopMove")
        else:
            # Unitree SportMode Move API: x forward, y left, z yaw rate.
            req = self.create_request(
                api_id=ROBOT_SPORT_API_ID_MOVE,
                parameters=json.dumps({"x": vx, "y": vy, "z": wz}),
            )
            self.get_logger().info(
                f"cmd_vel -> Move: x={vx:.3f}, y={vy:.3f}, z={wz:.3f}"
            )

        # Publish the request
        self.publisher.publish(req)
        self.request_count += 1
        self.current_request = req

    def timer_callback(self):
        """
        Timer callback to handle periodic command publishing and timeout.
        """
        if self.last_cmd_time is None:
            return

        age = (self.get_clock().now() - self.last_cmd_time).nanoseconds / 1e9
        if age >= self.cmd_vel_timeout_duration and not self.sent_idle_after_timeout:
            self.publish_idle_command()

        # Handle reset state
        if self.reset_state:
            self.reset_state = False
            self.publish_idle_command()

    def publish_idle_command(self):
        """Publishes a Unitree StopMove command."""
        req = self.create_request(api_id=ROBOT_SPORT_API_ID_STOPMOVE)
        self.publisher.publish(req)
        self.request_count += 1
        self.sent_idle_after_timeout = True
        self.get_logger().info("Published StopMove command")

    def log_stats(self):
        cmd_publishers = self.count_publishers(self.cmd_vel_topic)
        sport_subscribers = self.count_subscribers(self.request_topic)
        if self.last_cmd_time is None:
            age_text = "never"
        else:
            age = (self.get_clock().now() - self.last_cmd_time).nanoseconds / 1e9
            age_text = f"{age:.2f}s"
        vx, vy, wz = self.last_cmd
        self.get_logger().info(
            "bridge stats: "
            f"cmd_count={self.cmd_count}, request_count={self.request_count}, "
            f"cmd_publishers={cmd_publishers}, sport_subscribers={sport_subscribers}, "
            f"last_cmd_age={age_text}, last=({vx:.3f},{vy:.3f},{wz:.3f})"
        )

    def clean_velocity(self, value, limit):
        value = float(value)
        if not math.isfinite(value):
            return 0.0
        value = max(-limit, min(limit, value))
        return 0.0 if abs(value) < self.deadband else value

    def is_zero(self, value):
        return abs(value) < self.deadband

    # Service Callbacks
    def balance_stand_callback(self, request, response):
        self.publisher.publish(self.create_request(api_id=ROBOT_SPORT_API_ID_BALANCESTAND))
        self.request_count += 1
        self.reset_state = True
        self.get_logger().info("BalanceStand command sent")
        return response

    def stop_move_callback(self, request, response):
        self.publish_idle_command()
        self.get_logger().info("StopMove command sent")
        return response

    def stand_up_callback(self, request, response):
        self.publisher.publish(self.create_request(api_id=ROBOT_SPORT_API_ID_STANDUP))
        self.request_count += 1
        self.reset_state = True
        self.get_logger().info("Stand Up command sent")
        return response

    def lay_down_callback(self, request, response):
        self.publisher.publish(self.create_request(api_id=ROBOT_SPORT_API_ID_STANDDOWN))
        self.request_count += 1
        self.reset_state = True
        self.get_logger().info("Lay Down command sent")
        return response

    def recover_stand_callback(self, request, response):
        self.publisher.publish(self.create_request(api_id=ROBOT_SPORT_API_ID_RECOVERYSTAND))
        self.request_count += 1
        self.reset_state = True
        self.get_logger().info("Recover Stand command sent")
        return response

    def damping_callback(self, request, response):
        self.publisher.publish(self.create_request(api_id=ROBOT_SPORT_API_ID_DAMP))
        self.request_count += 1
        self.reset_state = True
        self.get_logger().info("Damping command sent")
        return response

    def dance1_callback(self, request, response):
        self.publisher.publish(self.create_request(api_id=ROBOT_SPORT_API_ID_DANCE1))
        self.request_count += 1
        self.reset_state = True
        self.get_logger().info("Dance1 command sent")
        return response

    def dance2_callback(self, request, response):
        self.publisher.publish(self.create_request(api_id=ROBOT_SPORT_API_ID_DANCE2))
        self.request_count += 1
        self.reset_state = True
        self.get_logger().info("Dance2 command sent")
        return response


def main(args=None):
    rclpy.init(args=args)
    node = Go2CmdProcessor()
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
