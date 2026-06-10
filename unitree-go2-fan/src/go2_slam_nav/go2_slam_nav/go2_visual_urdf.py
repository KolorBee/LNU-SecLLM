import sys
import xml.etree.ElementTree as ET


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: go2_visual_urdf URDF_PATH [ROOT_FRAME]")

    urdf_path = sys.argv[1]
    root_frame = sys.argv[2] if len(sys.argv) >= 3 else "base_link_visual"

    tree = ET.parse(urdf_path)
    robot = tree.getroot()

    for link in robot.findall("link"):
        if link.get("name") == "base_link":
            link.set("name", root_frame)

    for element in robot.iter():
        if element.tag in ("parent", "child") and element.get("link") == "base_link":
            element.set("link", root_frame)

    sys.stdout.write(ET.tostring(robot, encoding="unicode"))


if __name__ == "__main__":
    main()
