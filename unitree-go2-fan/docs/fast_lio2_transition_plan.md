# Unitree Go2 + Hesai JT128 转 FAST-LIO2 可行方案

## 当前定位

目前 `unitree-go2-fan` 已经把 Go2、Hesai JT128、RTAB-Map LiDAR 建图、RViz 可视化和 Nav2 导航初步串起来。这一版适合作为过渡平台：

- 验证雷达网络、点云话题、TF、Go2 里程计和 RViz/Nav2 基础链路。
- 产出 2D occupancy grid，方便短距离室内测试。
- 为后续 FAST-LIO2 提供可回退的基线。

但 RTAB-Map 当前主要依赖降采样后的 LiDAR ICP，在机器狗摇头、雷达安装轻微晃动、长巷道重复结构较多时，仍可能出现局部重影和漂移。下一阶段建议把 FAST-LIO2 作为主里程计接入，再让 RTAB-Map/Nav2 做地图管理和导航。

## 推荐总体架构

建议先采用“并行接入、逐步替换”的方式：

```text
Hesai JT128 /lidar_points
        |
        v
hesai_points_adapter
        |
        v
FAST-LIO2  <--- IMU, preferably rigidly mounted with LiDAR
        |
        +--> /lio_odom
        +--> /lio_path
        +--> /lio_cloud_registered
        +--> TF: lio_odom -> base_link 或 map_lio -> base_link

/lio_odom + filtered cloud
        |
        +--> RTAB-Map graph / loop closure / 2D grid
        |
        +--> Nav2 local/global costmap
```

第一阶段不要直接移除现有 RTAB-Map ICP 链路，而是保留当前 `mapping.sh` 作为基线，新增 `lio_mapping.sh` 或 `fast_lio.launch.py`。这样一旦 FAST-LIO2 参数、IMU 或时间同步没有调好，可以马上切回当前可用版本。

## 关键技术点

### 1. 点云适配

FAST-LIO2 对点云字段比较敏感，Hesai JT128 的 `/lidar_points` 需要确认以下字段：

```text
x, y, z
intensity
ring 或 line
timestamp / time / offset_time
```

如果 Hesai 驱动没有提供 FAST-LIO2 期望的逐点相对时间字段，需要写一个 `hesai_points_adapter`：

- 输入 `/lidar_points`
- 输出 `/points_raw` 或 `/hesai_points_lio`
- 保留 `x/y/z/intensity`
- 将 Hesai 点时间转换为 FAST-LIO2 可用的 `time` 或 `offset_time`
- 继续做近距离机身过滤和屋顶/地面高度过滤，但过滤强度要比 RViz 可视化更保守

### 2. IMU 选择

FAST-LIO2 的核心优势来自 LiDAR + IMU 紧耦合。建议优先级如下：

1. 独立外置 IMU，与 Hesai 雷达刚性固定在同一支架上。
2. 如果雷达或当前系统有可靠 `/lidar_imu`，优先测试它。
3. Go2 机身 IMU 可以作为过渡测试，但它不和雷达完全刚性共体，机器狗躯干晃动会引入误差。

如果只用 Go2 自带运动/里程计，不是真正的 LiDAR-inertial odometry，FAST-LIO2 的效果会被明显削弱。

### 3. 时间同步

必须记录并检查：

```bash
ros2 topic hz /lidar_points
ros2 topic hz /imu
ros2 topic echo /lidar_points --once --field header.stamp
ros2 topic echo /imu --once --field header.stamp
```

要求：

- LiDAR 和 IMU 时间不能长期相差数秒。
- 点云帧时间必须单调递增。
- 如果多机通信，主机、狗、雷达相关设备需要统一时间源。

### 4. TF 与 Nav2 接法

建议避免多个节点同时发布同一条 TF。初期可使用：

```text
base_link -> hesai_lidar: static transform
lio_odom -> base_link: FAST-LIO2 发布
map -> lio_odom: RTAB-Map 或后续定位模块发布
```

当前 `go2_odom_relay` 发布的 `odom -> base_link` 不要和 FAST-LIO2 同时抢同一条 `odom -> base_link`。切换到 LIO 模式时，需要把 Nav2 和 RTAB-Map 的 odom 输入改为 `/lio_odom`，并关闭或改名 Go2 原始 odom TF。

## 实施阶段

### 阶段 A：传感器审计

目标：确认 FAST-LIO2 必要输入是否具备。

输出：

- `/lidar_points` 字段清单
- LiDAR/IMU 频率
- LiDAR/IMU 时间差
- 雷达到 `base_link` 的外参
- 是否存在可靠外置 IMU 的结论

### 阶段 B：新增 LIO 分支

新增内容：

```text
src/fast_lio2 或 third_party/FAST_LIO2
src/go2_slam_nav/go2_slam_nav/hesai_points_adapter.py
src/go2_slam_nav/launch/fast_lio.launch.py
scripts/lio_mapping.sh
config/fast_lio2_hesai_jt128.yaml
```

目标：

- 不启动 RTAB-Map，仅启动 Hesai + adapter + FAST-LIO2 + RViz。
- RViz 中能看到 `/lio_odom`、`/lio_path`、`/lio_cloud_registered`。
- 机器狗静止时地图不漂，低速直行和原地转向时点云不明显撕裂。

### 阶段 C：FAST-LIO2 替代 RTAB-Map ICP 里程计

目标：

- RTAB-Map 不再自己通过 ICP 猜 odom，而是订阅 `/lio_odom`。
- RTAB-Map 继续负责图优化、回环和 2D 栅格输出。
- Nav2 继续使用 `/map`、`/map_updates`、costmap 和 goal 行为。

这样可以保留现有 Nav2/RViz/地图保存流程，同时把最容易漂的 LiDAR ICP odom 换成 LIO odom。

### 阶段 D：矿山巷道巡检增强

FAST-LIO2 本身不等于完整矿山巡检系统。长巷道容易出现重复结构和累计漂移，建议后续补：

- 回环检测：Scan Context、RTAB-Map graph 或 FAST-LIO-LC 类方案。
- 拓扑巡检图：巷道节点、岔路边、坡道边、禁行区。
- 语义/安全层：积水、落石、窄通道、低矮障碍物。
- 任务记录：巡检点照片/点云切片/气体传感器/温湿度记录。
- 失效策略：定位退化、雷达断流、网络断开、狗姿态异常时自动停止。

## 验收标准

### 室内短测

- 静止 2 分钟，`/lio_odom` 位移漂移小于 0.1 m。
- 低速走正方形，点云墙体重影明显少于当前 RTAB-Map ICP 版本。
- 原地左右转向，墙体不跟着大幅旋转。
- RViz 不因点云显示卡死。

### 巷道模拟测

- 直线 20-50 m 往返，轨迹能基本闭合。
- 经过相似墙面和长走廊时，局部地图不出现明显双墙。
- Nav2 可基于 LIO/RTAB 输出的 2D grid 发送目标点并安全停止。

## 风险与建议

- 最大风险不是 FAST-LIO2 代码本身，而是 IMU、点云逐点时间、外参和时间同步。
- 若没有可靠 IMU，FAST-LIO2 可能不如当前过渡方案稳定。
- 长巷道最终一定要考虑回环或拓扑约束，单靠 FAST-LIO2 仍会有累计漂移。
- 建议先新增分支，不要急着删掉现有 RTAB-Map 启动链路。

## 推荐下一步

1. 记录一包当前可用 RTAB-Map 基线 rosbag。
2. 检查 `/lidar_points` 点字段和 `/lidar_imu`、`/imu` 可用性。
3. 新增 `hesai_points_adapter`，先只做字段转换和时间字段验证。
4. 建立 `fast_lio.launch.py`，先跑纯 LIO，不接 Nav2。
5. LIO 稳定后，再把 RTAB-Map 的 odom 输入切换到 `/lio_odom`。
