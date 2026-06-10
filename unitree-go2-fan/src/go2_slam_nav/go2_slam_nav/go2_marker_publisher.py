import math

import rclpy
from geometry_msgs.msg import Point
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from visualization_msgs.msg import Marker, MarkerArray


class Go2MarkerPublisher(Node):
    def __init__(self):
        super().__init__("go2_marker_publisher")
        self.frame_id = self.declare_parameter("frame_id", "base_link").value
        self.topic = self.declare_parameter("topic", "/go2_marker").value
        publish_rate = float(self.declare_parameter("publish_rate", 5.0).value)
        publish_rate = max(1.0, publish_rate)
        self.publisher = self.create_publisher(MarkerArray, self.topic, 10)
        self.timer = self.create_timer(1.0 / publish_rate, self.publish_markers)

    def base_marker(self, marker_id, marker_type):
        marker = Marker()
        marker.header.frame_id = self.frame_id
        # A zero timestamp lets RViz use the latest available TF for this visual aid.
        marker.ns = "go2_body"
        marker.id = marker_id
        marker.type = marker_type
        marker.action = Marker.ADD
        marker.lifetime.sec = 0
        marker.frame_locked = True
        return marker

    def delete_marker(self, marker_id):
        marker = self.base_marker(marker_id, Marker.CUBE)
        marker.action = Marker.DELETE
        return marker

    def publish_markers(self):
        markers = MarkerArray()

        body = self.base_marker(0, Marker.CUBE)
        body.pose.position.x = 0.0
        body.pose.position.y = 0.0
        body.pose.position.z = 0.28
        body.pose.orientation.w = 1.0
        body.scale.x = 0.78
        body.scale.y = 0.36
        body.scale.z = 0.20
        body.color.r = 0.05
        body.color.g = 0.75
        body.color.b = 1.0
        body.color.a = 0.72
        markers.markers.append(body)

        heading = self.base_marker(1, Marker.ARROW)
        heading.points = [
            Point(x=-0.15, y=0.0, z=0.45),
            Point(x=0.72, y=0.0, z=0.45),
        ]
        heading.scale.x = 0.08
        heading.scale.y = 0.18
        heading.scale.z = 0.24
        heading.color.r = 1.0
        heading.color.g = 0.82
        heading.color.b = 0.05
        heading.color.a = 0.95
        markers.markers.append(heading)

        lidar = self.base_marker(2, Marker.CYLINDER)
        lidar.pose.position.x = 0.0
        lidar.pose.position.y = 0.0
        lidar.pose.position.z = 0.55
        lidar.pose.orientation.w = 1.0
        lidar.scale.x = 0.18
        lidar.scale.y = 0.18
        lidar.scale.z = 0.24
        lidar.color.r = 0.1
        lidar.color.g = 1.0
        lidar.color.b = 0.25
        lidar.color.a = 0.85
        markers.markers.append(lidar)

        footprint = self.base_marker(3, Marker.LINE_STRIP)
        footprint.pose.orientation.w = 1.0
        footprint.scale.x = 0.04
        footprint.points = [
            Point(x=0.42, y=0.26, z=0.02),
            Point(x=0.42, y=-0.26, z=0.02),
            Point(x=-0.42, y=-0.26, z=0.02),
            Point(x=-0.42, y=0.26, z=0.02),
            Point(x=0.42, y=0.26, z=0.02),
        ]
        footprint.color.r = 1.0
        footprint.color.g = 0.35
        footprint.color.b = 0.0
        footprint.color.a = 0.95
        markers.markers.append(footprint)

        range_ring = self.base_marker(4, Marker.LINE_STRIP)
        range_ring.pose.orientation.w = 1.0
        range_ring.scale.x = 0.045
        radius = 1.25
        range_ring.points = [
            Point(
                x=math.cos(theta) * radius,
                y=math.sin(theta) * radius,
                z=0.03,
            )
            for theta in [2.0 * math.pi * i / 48 for i in range(49)]
        ]
        range_ring.color.r = 0.05
        range_ring.color.g = 0.9
        range_ring.color.b = 1.0
        range_ring.color.a = 0.45
        markers.markers.append(range_ring)

        mast = self.base_marker(5, Marker.LINE_STRIP)
        mast.pose.orientation.w = 1.0
        mast.scale.x = 0.09
        mast.points = [
            Point(x=0.0, y=0.0, z=0.55),
            Point(x=0.0, y=0.0, z=2.10),
        ]
        mast.color.r = 1.0
        mast.color.g = 0.0
        mast.color.b = 1.0
        mast.color.a = 0.95
        markers.markers.append(mast)

        beacon = self.base_marker(6, Marker.SPHERE)
        beacon.pose.position.x = 0.0
        beacon.pose.position.y = 0.0
        beacon.pose.position.z = 2.10
        beacon.pose.orientation.w = 1.0
        beacon.scale.x = 0.45
        beacon.scale.y = 0.45
        beacon.scale.z = 0.45
        beacon.color.r = 1.0
        beacon.color.g = 0.92
        beacon.color.b = 0.0
        beacon.color.a = 0.95
        markers.markers.append(beacon)

        markers.markers.append(self.delete_marker(7))

        vertical_arrow = self.base_marker(8, Marker.ARROW)
        vertical_arrow.points = [
            Point(x=0.0, y=0.0, z=2.65),
            Point(x=0.0, y=0.0, z=1.05),
        ]
        vertical_arrow.scale.x = 0.10
        vertical_arrow.scale.y = 0.30
        vertical_arrow.scale.z = 0.35
        vertical_arrow.color.r = 1.0
        vertical_arrow.color.g = 0.05
        vertical_arrow.color.b = 0.05
        vertical_arrow.color.a = 0.95
        markers.markers.append(vertical_arrow)

        self.publisher.publish(markers)


def main(args=None):
    rclpy.init(args=args)
    node = Go2MarkerPublisher()
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
