import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import JointState


class Go2JointStatePublisher(Node):
    def __init__(self):
        super().__init__("go2_joint_state_publisher")
        self.declare_parameter("output_topic", "/joint_states")
        output_topic = str(self.get_parameter("output_topic").value)
        self.publisher = self.create_publisher(JointState, output_topic, 10)
        self.timer = self.create_timer(0.1, self.publish_joint_states)
        self.joint_names = [
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
        self.standing_pose = [
            0.0,
            0.75,
            -1.45,
            0.0,
            0.75,
            -1.45,
            0.0,
            0.85,
            -1.55,
            0.0,
            0.85,
            -1.55,
        ]

    def publish_joint_states(self):
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = self.joint_names
        msg.position = self.standing_pose
        self.publisher.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = Go2JointStatePublisher()
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
