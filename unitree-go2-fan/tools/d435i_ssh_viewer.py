#!/usr/bin/env python3
import argparse
import json
import os
import shlex
import struct
import subprocess
import sys
import tempfile
import textwrap
import time

import cv2
import numpy as np


REMOTE_CPP = r'''
#include <librealsense2/rs.hpp>
#include <opencv2/opencv.hpp>

#include <chrono>
#include <cstdint>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::string arg_value(int argc, char** argv, const std::string& name,
                      const std::string& fallback) {
  for (int i = 1; i + 1 < argc; ++i) {
    if (argv[i] == name) {
      return argv[i + 1];
    }
  }
  return fallback;
}

bool stream_enabled(const std::string& streams, const std::string& name) {
  std::stringstream ss(streams);
  std::string item;
  while (std::getline(ss, item, ',')) {
    if (item == name) {
      return true;
    }
  }
  return false;
}

uint64_t now_ms() {
  auto now = std::chrono::steady_clock::now().time_since_epoch();
  return static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::milliseconds>(now).count());
}

void write_u32(uint32_t value) {
  std::cout.write(reinterpret_cast<const char*>(&value), sizeof(value));
}

void send_jpeg(const std::string& stream_name, const cv::Mat& image,
               int quality, uint64_t seq) {
  std::vector<uchar> encoded;
  std::vector<int> params = {cv::IMWRITE_JPEG_QUALITY, quality};
  if (!cv::imencode(".jpg", image, encoded, params)) {
    throw std::runtime_error("cv::imencode failed for " + stream_name);
  }

  std::ostringstream header;
  header << "{\"stream\":\"" << stream_name << "\","
         << "\"width\":" << image.cols << ","
         << "\"height\":" << image.rows << ","
         << "\"format\":\"jpg\","
         << "\"seq\":" << seq << ","
         << "\"timestamp_ms\":" << now_ms() << "}";
  const std::string header_text = header.str();

  const char magic[4] = {'G', '2', 'D', '4'};
  std::cout.write(magic, 4);
  write_u32(static_cast<uint32_t>(header_text.size()));
  std::cout.write(header_text.data(), static_cast<std::streamsize>(header_text.size()));
  write_u32(static_cast<uint32_t>(encoded.size()));
  std::cout.write(reinterpret_cast<const char*>(encoded.data()),
                  static_cast<std::streamsize>(encoded.size()));
  std::cout.flush();
}

cv::Mat frame_to_mat_bgr(const rs2::video_frame& frame) {
  const int width = frame.get_width();
  const int height = frame.get_height();
  cv::Mat mat(cv::Size(width, height), CV_8UC3,
              const_cast<void*>(frame.get_data()), cv::Mat::AUTO_STEP);
  return mat.clone();
}

cv::Mat frame_to_mat_gray(const rs2::video_frame& frame) {
  const int width = frame.get_width();
  const int height = frame.get_height();
  cv::Mat mat(cv::Size(width, height), CV_8UC1,
              const_cast<void*>(frame.get_data()), cv::Mat::AUTO_STEP);
  return mat.clone();
}

}  // namespace

int main(int argc, char** argv) {
  try {
    std::ios::sync_with_stdio(false);

    const int width = std::stoi(arg_value(argc, argv, "--width", "640"));
    const int height = std::stoi(arg_value(argc, argv, "--height", "480"));
    const int fps = std::stoi(arg_value(argc, argv, "--fps", "15"));
    const int quality = std::stoi(arg_value(argc, argv, "--quality", "80"));
    const std::string streams =
        arg_value(argc, argv, "--streams", "color,depth,infra1");

    const bool use_color = stream_enabled(streams, "color");
    const bool use_depth = stream_enabled(streams, "depth");
    const bool use_infra1 = stream_enabled(streams, "infra1");
    const bool use_infra2 = stream_enabled(streams, "infra2");

    if (!use_color && !use_depth && !use_infra1 && !use_infra2) {
      throw std::runtime_error("no streams enabled");
    }

    rs2::pipeline pipe;
    rs2::config cfg;
    if (use_color) {
      cfg.enable_stream(RS2_STREAM_COLOR, width, height, RS2_FORMAT_BGR8, fps);
    }
    if (use_depth) {
      cfg.enable_stream(RS2_STREAM_DEPTH, width, height, RS2_FORMAT_Z16, fps);
    }
    if (use_infra1) {
      cfg.enable_stream(RS2_STREAM_INFRARED, 1, width, height, RS2_FORMAT_Y8, fps);
    }
    if (use_infra2) {
      cfg.enable_stream(RS2_STREAM_INFRARED, 2, width, height, RS2_FORMAT_Y8, fps);
    }

    rs2::colorizer colorizer;
    pipe.start(cfg);
    std::cerr << "[go2-d435i] streaming " << streams << " "
              << width << "x" << height << "@" << fps << std::endl;

    uint64_t seq = 0;
    while (true) {
      rs2::frameset frames = pipe.wait_for_frames();
      ++seq;

      if (use_color) {
        rs2::video_frame color = frames.get_color_frame();
        if (color) {
          send_jpeg("d435i_color", frame_to_mat_bgr(color), quality, seq);
        }
      }

      if (use_depth) {
        rs2::depth_frame depth = frames.get_depth_frame();
        if (depth) {
          rs2::video_frame colored = colorizer.colorize(depth);
          cv::Mat rgb(cv::Size(colored.get_width(), colored.get_height()), CV_8UC3,
                      const_cast<void*>(colored.get_data()), cv::Mat::AUTO_STEP);
          cv::Mat bgr;
          cv::cvtColor(rgb, bgr, cv::COLOR_RGB2BGR);
          send_jpeg("d435i_depth", bgr, quality, seq);
        }
      }

      if (use_infra1) {
        rs2::video_frame infra = frames.get_infrared_frame(1);
        if (infra) {
          send_jpeg("d435i_infra1", frame_to_mat_gray(infra), quality, seq);
        }
      }

      if (use_infra2) {
        rs2::video_frame infra = frames.get_infrared_frame(2);
        if (infra) {
          send_jpeg("d435i_infra2", frame_to_mat_gray(infra), quality, seq);
        }
      }
    }
  } catch (const std::exception& exc) {
    std::cerr << "[go2-d435i] ERROR: " << exc.what() << std::endl;
    return 1;
  }
}
'''


def parse_args():
    parser = argparse.ArgumentParser(
        description="Display the Go2 Orin-attached RealSense D435i over SSH."
    )
    parser.add_argument("--host", default=os.environ.get("ORIN_HOST", "192.168.123.18"))
    parser.add_argument("--user", default=os.environ.get("ORIN_USER", "unitree"))
    parser.add_argument("--width", type=int, default=int(os.environ.get("D435I_WIDTH", "640")))
    parser.add_argument("--height", type=int, default=int(os.environ.get("D435I_HEIGHT", "480")))
    parser.add_argument("--fps", type=int, default=int(os.environ.get("D435I_FPS", "15")))
    parser.add_argument("--quality", type=int, default=int(os.environ.get("D435I_JPEG_QUALITY", "80")))
    parser.add_argument(
        "--streams",
        default=os.environ.get("D435I_STREAMS", "color,depth,infra1"),
        help="Comma list: color,depth,infra1,infra2",
    )
    parser.add_argument("--remote-src", default="/tmp/go2_d435i_streamer.cpp")
    parser.add_argument("--remote-bin", default="/tmp/go2_d435i_streamer")
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--no-display", action="store_true")
    parser.add_argument(
        "--frames",
        type=int,
        default=int(os.environ.get("D435I_TEST_FRAMES", "0")),
        help="Stop after this many decoded frames; 0 means run until closed.",
    )
    return parser.parse_args()


def run_checked(cmd, **kwargs):
    print("+ " + " ".join(shlex.quote(str(part)) for part in cmd), file=sys.stderr)
    subprocess.run(cmd, check=True, **kwargs)


def ssh_options(args):
    safe_host = "".join(ch if ch.isalnum() else "_" for ch in args.host)
    safe_user = "".join(ch if ch.isalnum() else "_" for ch in args.user)
    control_path = f"/tmp/go2_d435i_ssh_{safe_user}_{safe_host}"
    return [
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ControlMaster=auto",
        "-o",
        f"ControlPath={control_path}",
        "-o",
        "ControlPersist=10m",
    ]


def upload_and_build(args, target, ssh_opts):
    with tempfile.NamedTemporaryFile("w", suffix=".cpp", delete=False) as handle:
        handle.write(REMOTE_CPP)
        local_src = handle.name

    try:
        run_checked([
            "scp",
            *ssh_opts,
            local_src,
            f"{target}:{args.remote_src}",
        ])

        compile_cmd = (
            f"g++ -std=c++17 {shlex.quote(args.remote_src)} "
            f"-o {shlex.quote(args.remote_bin)} "
            "$(pkg-config --cflags --libs realsense2 opencv4)"
        )
        run_checked([
            "ssh",
            *ssh_opts,
            target,
            compile_cmd,
        ])
    finally:
        try:
            os.unlink(local_src)
        except OSError:
            pass


def read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            if not data:
                return None
            raise EOFError("stream ended mid-frame")
        data.extend(chunk)
    return bytes(data)


def read_frame(stream):
    magic = read_exact(stream, 4)
    if magic is None:
        return None
    if magic != b"G2D4":
        raise ValueError(f"bad stream magic: {magic!r}")

    header_len = struct.unpack("<I", read_exact(stream, 4))[0]
    header = json.loads(read_exact(stream, header_len).decode("utf-8"))
    payload_len = struct.unpack("<I", read_exact(stream, 4))[0]
    payload = read_exact(stream, payload_len)
    if payload is None:
        return None
    return header, payload


def ssh_stream(args, target, ssh_opts):
    remote_cmd = [
        args.remote_bin,
        "--width",
        str(args.width),
        "--height",
        str(args.height),
        "--fps",
        str(args.fps),
        "--quality",
        str(args.quality),
        "--streams",
        args.streams,
    ]
    quoted_remote = " ".join(shlex.quote(part) for part in remote_cmd)
    cmd = [
        "ssh",
        *ssh_opts,
        target,
        quoted_remote,
    ]
    print("+ " + " ".join(shlex.quote(part) for part in cmd), file=sys.stderr)
    return subprocess.Popen(cmd, stdout=subprocess.PIPE)


def main():
    args = parse_args()
    target = f"{args.user}@{args.host}"
    ssh_opts = ssh_options(args)

    if not args.no_build:
        upload_and_build(args, target, ssh_opts)

    proc = ssh_stream(args, target, ssh_opts)
    windows = set()
    decoded = 0
    started = time.monotonic()

    try:
        while True:
            item = read_frame(proc.stdout)
            if item is None:
                break

            header, payload = item
            array = np.frombuffer(payload, dtype=np.uint8)
            frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
            if frame is None:
                print(f"[go2-d435i] failed to decode {header}", file=sys.stderr)
                continue

            decoded += 1
            name = header.get("stream", "d435i")
            if args.no_display:
                if decoded <= 5:
                    print(f"[go2-d435i] decoded {name} {frame.shape} seq={header.get('seq')}")
            else:
                if name not in windows:
                    cv2.namedWindow(name, cv2.WINDOW_NORMAL)
                    windows.add(name)
                cv2.imshow(name, frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break

            if args.frames > 0 and decoded >= args.frames:
                break
    finally:
        elapsed = max(0.001, time.monotonic() - started)
        print(
            f"[go2-d435i] decoded {decoded} frames in {elapsed:.1f}s "
            f"({decoded / elapsed:.1f} display frames/s)",
            file=sys.stderr,
        )
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        if not args.no_display:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
