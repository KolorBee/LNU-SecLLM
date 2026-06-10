import time

import cv2
import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import CompressedImage, Image


RAW_IMAGE_TYPE = "sensor_msgs/msg/Image"
COMPRESSED_IMAGE_TYPE = "sensor_msgs/msg/CompressedImage"
UNITREE_FRONT_VIDEO_TYPE = "unitree_go/msg/Go2FrontVideoData"


class Go2CameraViewer(Node):
    def __init__(self):
        super().__init__("go2_camera_viewer")
        self.declare_parameter("image_topic", "auto")
        self.declare_parameter("compressed", False)
        self.declare_parameter("window_name", "Go2 Camera")
        self.declare_parameter("max_display_rate", 30.0)
        self.declare_parameter("prefer_keywords", "front,camera,image,color")
        self.declare_parameter("fallback_to_auto", True)
        self.declare_parameter("max_video_packet_size", 2097152)
        self.declare_parameter("unitree_stream", "video720p")
        self.declare_parameter("unitree_frame_timeout", 0.2)

        self.image_topic = str(self.get_parameter("image_topic").value)
        self.compressed = bool(self.get_parameter("compressed").value)
        self.window_name = str(self.get_parameter("window_name").value)
        self.max_display_rate = max(
            1.0, float(self.get_parameter("max_display_rate").value)
        )
        self.prefer_keywords = [
            item.strip().lower()
            for item in str(self.get_parameter("prefer_keywords").value).split(",")
            if item.strip()
        ]
        self.fallback_to_auto = bool(self.get_parameter("fallback_to_auto").value)
        self.max_video_packet_size = int(
            self.get_parameter("max_video_packet_size").value
        )
        self.unitree_stream = str(self.get_parameter("unitree_stream").value)
        self.unitree_frame_timeout = max(
            0.02, float(self.get_parameter("unitree_frame_timeout").value)
        )
        self.min_period = 1.0 / self.max_display_rate
        self.last_display_time = 0.0
        self.subscription = None
        self.discovery_timer = None
        self.h264_decoder = None
        self.current_unitree_time_frame = None
        self.current_unitree_parts = []
        self.current_unitree_started_at = 0.0
        self.bad_video_packets = 0
        self.decoded_video_frames = 0
        self.video_packets = 0

        self.image_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.video_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self.stats_timer = self.create_timer(5.0, self.log_stats)
        self.unitree_flush_timer = self.create_timer(0.05, self.flush_stale_unitree_frame)

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)

        if self.image_topic == "auto":
            self.discovery_timer = self.create_timer(1.0, self.discover_topic)
            self.get_logger().info("waiting for a ROS image/video topic...")
        else:
            self.discovery_timer = self.create_timer(1.0, self.resolve_requested_topic)
            self.resolve_requested_topic()

    def discover_topic(self):
        topics = self.get_topic_names_and_types()
        candidates = []
        for topic, types in topics:
            if RAW_IMAGE_TYPE in types:
                candidates.append((topic, False, self.topic_score(topic)))
            if COMPRESSED_IMAGE_TYPE in types:
                candidates.append((topic, True, self.topic_score(topic)))
            if UNITREE_FRONT_VIDEO_TYPE in types:
                candidates.append((topic, "unitree_front_video", self.topic_score(topic) + 20))

        if not candidates:
            self.get_logger().info(
                "no Image/CompressedImage/Go2FrontVideoData topic found yet",
                throttle_duration_sec=5.0,
            )
            return

        topic, topic_kind, _ = self.best_candidate(candidates)
        self.subscribe(topic, topic_kind)
        if self.discovery_timer is not None:
            self.destroy_timer(self.discovery_timer)
            self.discovery_timer = None

    def resolve_requested_topic(self):
        topics = dict(self.get_topic_names_and_types())
        types = topics.get(self.image_topic, [])
        if RAW_IMAGE_TYPE in types:
            self.subscribe(self.image_topic, False)
        elif COMPRESSED_IMAGE_TYPE in types:
            self.subscribe(self.image_topic, True)
        elif UNITREE_FRONT_VIDEO_TYPE in types:
            self.subscribe(self.image_topic, "unitree_front_video")
        elif not self.fallback_to_auto:
            self.subscribe(self.image_topic, self.compressed)
        else:
            self.get_logger().warn(
                f"{self.image_topic} is not available as an image topic; "
                "falling back to auto discovery",
                throttle_duration_sec=5.0,
            )
            self.discover_topic()
            return

        if self.discovery_timer is not None:
            self.destroy_timer(self.discovery_timer)
            self.discovery_timer = None

    @staticmethod
    def best_candidate(candidates):
        candidates.sort(key=lambda item: item[2], reverse=True)
        return candidates[0]

    def topic_score(self, topic):
        lower = topic.lower()
        score = 0
        for index, keyword in enumerate(self.prefer_keywords):
            if keyword in lower:
                score += 10 - index
        if "compressed" in lower:
            score -= 1
        return score

    def subscribe(self, topic, topic_kind):
        if topic_kind == "unitree_front_video":
            msg_type = self.load_unitree_front_video_type()
            callback = self.on_unitree_front_video
        elif topic_kind:
            msg_type = CompressedImage
            callback = self.on_compressed_image
        else:
            msg_type = Image
            callback = self.on_raw_image

        qos = self.video_qos if topic_kind == "unitree_front_video" else self.image_qos
        self.subscription = self.create_subscription(msg_type, topic, callback, qos)
        self.get_logger().info(f"displaying {topic_kind or 'raw'} topic {topic}")

    @staticmethod
    def load_unitree_front_video_type():
        try:
            from unitree_go.msg import Go2FrontVideoData  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Cannot import unitree_go.msg.Go2FrontVideoData. Source "
                "/home/star/unitree_ros2/setup_go2.sh before running the viewer."
            ) from exc
        return Go2FrontVideoData

    def on_raw_image(self, msg):
        if not self.should_display():
            return
        try:
            frame = self.raw_image_to_bgr(msg)
            self.show(frame)
        except Exception as exc:
            self.get_logger().error(f"failed to decode raw image: {exc}")

    def on_compressed_image(self, msg):
        if not self.should_display():
            return
        try:
            array = np.frombuffer(msg.data, dtype=np.uint8)
            frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError("cv2.imdecode returned None")
            self.show(frame)
        except Exception as exc:
            self.get_logger().error(f"failed to decode compressed image: {exc}")

    def on_unitree_front_video(self, msg):
        packet = self.pick_video_packet(msg)
        if packet is None:
            return
        self.video_packets += 1

        try:
            time_frame = int(getattr(msg, "time_frame", 0))
            if (
                self.current_unitree_time_frame is not None
                and time_frame != self.current_unitree_time_frame
            ):
                self.flush_unitree_frame()

            if self.current_unitree_time_frame is None:
                self.current_unitree_time_frame = time_frame
                self.current_unitree_started_at = time.monotonic()

            self.current_unitree_parts.append(packet)
        except Exception as exc:
            self.get_logger().warn(
                f"failed to buffer Unitree front video packet: {exc}",
                throttle_duration_sec=5.0,
            )

    def pick_video_packet(self, msg):
        fields = [self.unitree_stream]
        fields.extend(
            field
            for field in ("video720p", "video360p", "video180p")
            if field != self.unitree_stream
        )

        for field in fields:
            data = getattr(msg, field, None)
            if data is None:
                continue
            size = len(data)
            if size <= 0:
                continue
            if size > self.max_video_packet_size:
                self.bad_video_packets += 1
                self.get_logger().warn(
                    f"skip malformed {field} packet size={size}; "
                    f"bad_packets={self.bad_video_packets}",
                    throttle_duration_sec=5.0,
                )
                continue
            packet = bytes(data)
            normalized = self.normalize_h264_packet(packet)
            return normalized if normalized is not None else packet
        return None

    @staticmethod
    def try_decode_still_image(packet):
        if not packet.startswith((b"\xff\xd8", b"\x89PNG", b"BM")):
            return None
        array = np.frombuffer(packet, dtype=np.uint8)
        return cv2.imdecode(array, cv2.IMREAD_COLOR)

    def decode_h264(self, packet):
        if self.h264_decoder is None:
            try:
                import av
            except ImportError as exc:
                raise RuntimeError(
                    "PyAV is required for Unitree front video H.264 packets. "
                    "Install it with: /usr/bin/python3 -m pip install --user av"
                ) from exc
            self.h264_decoder = av.CodecContext.create("h264", "r")

        frames = []
        for av_packet in self.h264_decoder.parse(packet):
            for frame in self.h264_decoder.decode(av_packet):
                frames.append(frame.to_ndarray(format="bgr24"))
        return frames

    def flush_unitree_frame(self):
        if not self.current_unitree_parts:
            self.current_unitree_time_frame = None
            return

        packet = b"".join(self.current_unitree_parts)
        self.current_unitree_parts = []
        self.current_unitree_time_frame = None
        self.current_unitree_started_at = 0.0

        image = self.try_decode_still_image(packet)
        if image is not None:
            self.show_if_ready(image)
            return

        try:
            frames = self.decode_h264(packet)
        except Exception as exc:
            self.bad_video_packets += 1
            self.get_logger().warn(
                f"failed to decode assembled Unitree H.264 frame: {exc}",
                throttle_duration_sec=5.0,
            )
            return

        if not frames:
            return

        for frame in frames:
            self.decoded_video_frames += 1
            self.show_if_ready(frame)

    def flush_stale_unitree_frame(self):
        if not self.current_unitree_parts:
            return
        if time.monotonic() - self.current_unitree_started_at >= self.unitree_frame_timeout:
            self.flush_unitree_frame()

    @staticmethod
    def normalize_h264_packet(packet):
        for marker in (b"\x00\x00\x00\x01", b"\x00\x00\x01"):
            index = packet.find(marker)
            if index >= 0:
                return packet[index:]
        return None

    def log_stats(self):
        if self.video_packets:
            self.get_logger().info(
                "front video stats: "
                f"packets={self.video_packets}, "
                f"decoded_frames={self.decoded_video_frames}, "
                f"bad_packets={self.bad_video_packets}, "
                f"buffered_parts={len(self.current_unitree_parts)}",
                throttle_duration_sec=5.0,
            )

    def should_display(self):
        now = time.monotonic()
        if now - self.last_display_time < self.min_period:
            return False
        self.last_display_time = now
        return True

    def show(self, frame):
        cv2.imshow(self.window_name, frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q")):
            self.get_logger().info("viewer closed by keyboard")
            rclpy.shutdown()

    def show_if_ready(self, frame):
        if self.should_display():
            self.show(frame)

    @staticmethod
    def raw_image_to_bgr(msg):
        encoding = msg.encoding.lower()
        data = memoryview(msg.data)

        if encoding in ("bgr8", "rgb8", "bgra8", "rgba8"):
            channels = 4 if "a" in encoding else 3
            row = np.frombuffer(data, dtype=np.uint8).reshape(msg.height, msg.step)
            image = row[:, : msg.width * channels].reshape(
                msg.height, msg.width, channels
            )
            if encoding == "rgb8":
                return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            if encoding == "rgba8":
                return cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
            if encoding == "bgra8":
                return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
            return image.copy()

        if encoding in ("mono8", "8uc1"):
            row = np.frombuffer(data, dtype=np.uint8).reshape(msg.height, msg.step)
            return row[:, : msg.width].copy()

        if encoding in ("16uc1", "mono16"):
            row_values = msg.step // 2
            row = np.frombuffer(data, dtype=np.uint16).reshape(msg.height, row_values)
            depth = row[:, : msg.width]
            depth8 = cv2.convertScaleAbs(depth, alpha=255.0 / max(1, int(depth.max())))
            return cv2.applyColorMap(depth8, cv2.COLORMAP_TURBO)

        if encoding == "32fc1":
            row_values = msg.step // 4
            row = np.frombuffer(data, dtype=np.float32).reshape(msg.height, row_values)
            depth = row[:, : msg.width]
            finite = np.nan_to_num(depth, nan=0.0, posinf=0.0, neginf=0.0)
            max_value = float(np.max(finite)) if finite.size else 1.0
            depth8 = cv2.convertScaleAbs(finite, alpha=255.0 / max(1e-6, max_value))
            return cv2.applyColorMap(depth8, cv2.COLORMAP_TURBO)

        raise ValueError(f"unsupported image encoding {msg.encoding!r}")


def main(args=None):
    rclpy.init(args=args)
    node = Go2CameraViewer()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            cv2.destroyAllWindows()
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
