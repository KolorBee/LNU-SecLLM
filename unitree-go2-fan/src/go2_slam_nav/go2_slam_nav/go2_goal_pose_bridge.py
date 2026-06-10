import math

import rclpy
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node


def yaw_from_quaternion(quaternion):
    x = quaternion.x
    y = quaternion.y
    z = quaternion.z
    w = quaternion.w
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


class Go2GoalPoseBridge(Node):
    def __init__(self):
        super().__init__("go2_goal_pose_bridge")
        self.declare_parameter("goal_pose_topic", "/goal_pose")
        self.declare_parameter("navigate_action_name", "/navigate_to_pose")
        self.declare_parameter("default_frame_id", "map")
        self.declare_parameter("server_wait_timeout", 2.0)

        self.goal_pose_topic = self.get_parameter("goal_pose_topic").value
        self.navigate_action_name = self.get_parameter("navigate_action_name").value
        self.default_frame_id = self.get_parameter("default_frame_id").value
        self.server_wait_timeout = max(
            0.1,
            float(self.get_parameter("server_wait_timeout").value),
        )

        self.action_client = ActionClient(
            self,
            NavigateToPose,
            self.navigate_action_name,
        )
        self.subscription = self.create_subscription(
            PoseStamped,
            self.goal_pose_topic,
            self.goal_callback,
            10,
        )
        self.goal_count = 0

        self.get_logger().info(
            f"Forwarding {self.goal_pose_topic} -> "
            f"{self.navigate_action_name} NavigateToPose action"
        )

    def goal_callback(self, msg):
        self.goal_count += 1
        if not msg.header.frame_id:
            msg.header.frame_id = self.default_frame_id
        if msg.header.stamp.sec == 0 and msg.header.stamp.nanosec == 0:
            msg.header.stamp = self.get_clock().now().to_msg()

        pos = msg.pose.position
        yaw = yaw_from_quaternion(msg.pose.orientation)
        self.get_logger().info(
            f"goal_pose #{self.goal_count}: frame={msg.header.frame_id}, "
            f"x={pos.x:.3f}, y={pos.y:.3f}, yaw={yaw:.3f}"
        )

        if not self.action_client.wait_for_server(timeout_sec=self.server_wait_timeout):
            self.get_logger().warn(
                f"{self.navigate_action_name} action server is not available; "
                "goal was not sent"
            )
            return

        goal = NavigateToPose.Goal()
        goal.pose = msg
        future = self.action_client.send_goal_async(goal)
        future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        try:
            goal_handle = future.result()
        except Exception as exc:
            self.get_logger().error(f"failed to send NavigateToPose goal: {exc}")
            return

        if not goal_handle.accepted:
            self.get_logger().warn("NavigateToPose goal rejected")
            return

        self.get_logger().info("NavigateToPose goal accepted")
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.goal_result_callback)

    def goal_result_callback(self, future):
        try:
            result = future.result()
        except Exception as exc:
            self.get_logger().error(f"failed to get NavigateToPose result: {exc}")
            return

        status = getattr(result, "status", "unknown")
        self.get_logger().info(f"NavigateToPose finished with status={status}")


def main(args=None):
    rclpy.init(args=args)
    node = Go2GoalPoseBridge()
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
