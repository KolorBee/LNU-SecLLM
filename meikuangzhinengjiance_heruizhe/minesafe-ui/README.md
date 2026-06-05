# 🪨 MineSafe AI — Intelligent Autonomous Mining Safety Platform

> **ROS-Enabled Cognitive Digital Twin System for Underground Mining Hazard Detection & Navigation**  
> Built in collaboration with **Tata Steel Mining** | Data sourced from **Ballari, Karnataka**

---

## 🧠 What is MineSafe AI?

MineSafe AI is a **real-world autonomous safety and navigation platform** designed for underground mining environments such as iron ore, manganese ore, and coal mines.

Mining environments are some of the most dangerous workplaces on earth — low visibility, extreme dust, unpredictable rockfalls, and complex underground geometry make every operation a risk. MineSafe AI tackles this head-on by combining:

- 🎯 **AI-powered object detection** (YOLO) trained on real mining data
- 🧬 **Cognitive Digital Twin** that *thinks*, not just visualizes
- 🗺️ **Risk-aware path navigation** with live Green / Yellow / Red route mapping
- 📡 **LoRa communication** for deep underground data transmission
- 🤖 **ROS architecture** for real-time autonomous decision-making

---

## 🌍 Real-World Impact

This project was built with real data — not just simulations.

| Data Source | Details |
|---|---|
| 🏭 Tata Steel Mining | In-person surveys with mining engineers |
| 📍 Ballari, Karnataka | Iron ore mining datasets from data.gov.in |
| 📊 Kaggle & IEEE | Mining research publications and datasets |
| 💥 Geological Records | Historical blasting logs, drilling records |

---

## ⚙️ System Architecture

The platform operates across **3 intelligent modules**, all coordinated through a ROS framework:

### Module 1 — Hazardous Object Detection
- YOLO-based deep learning model trained on mining-specific datasets
- Multi-modal sensor fusion: **Thermal cameras + LiDAR + Radar**
- Detects workers, machinery, falling rocks, and structural cracks in real time
- Adaptive confidence scoring based on **dust density and lighting conditions**

### Module 2 — Cognitive Digital Twin
- Reconstructs underground soil and rock stratification **without physical excavation**
- Uses historical geological data, blasting records, and sensor profiles
- Color-coded multi-layer 3D visualization (5+ underground layers)
- **AI-driven reasoning** for predictive hazard alerts:
  - Rockfall probability
  - Landslide likelihood
  - Structural weakening warnings

### Module 3 — Path Memory & Risk Navigation
- SLAM-based underground mapping via ROS
- Persistent path memory storage
- Dynamic route classification:
  - 🟢 **Green** — Safest and nearest route
  - 🟡 **Yellow** — Moderately safe
  - 🔴 **Red** — High-risk or distant
- Powers autonomous navigation, emergency evacuation, and vehicle routing

---

## 🛠️ Tech Stack

### Frontend
| Technology | Purpose |
|---|---|
| React | UI framework |
| Tailwind CSS | Styling |
| Vercel | Deployment |

### Backend
| Technology | Purpose |
|---|---|
| Render | Backend deployment |

### AI / Robotics Core
| Technology | Purpose |
|---|---|
| ROS (Robot Operating System) | Core autonomy, modular control, communication |
| YOLO | Real-time object detection in extreme environments |
| SLAM | Underground mapping and localization |
| LiDAR + Radar + Thermal | Environmental perception and sensor fusion |
| Machine Learning & Time-Series Analysis | Hazard prediction models |
| Computer Vision | Layer visualization and object classification |
| LoRa | Long-range, low-power underground communication |

---

## 🚀 Key Features

- ✅ Real-time hazard detection under extreme low-visibility conditions
- ✅ Predictive rockfall and landslide alerts before they happen
- ✅ Autonomous underground navigation with risk-classified routes
- ✅ Digital Twin that actively reasons — not just a static 3D model
- ✅ LoRa-enabled communication deep underground
- ✅ ROS-integrated modular architecture for scalability
- ✅ Validated with real data from Tata Steel mining sites

---

## 📊 Results

- 🎯 Improved hazard detection accuracy in dust-heavy, low-light environments
- ⚡ Real-time Digital Twin visualization with proactive warning system
- 🛡️ Early alerts for landslides and rockfalls before critical events
- 🗺️ Optimized safe path recommendations for autonomous mining vehicles
- 👷 Reduced human exposure to life-threatening underground conditions

---

## 🔭 Future Scope

- Reinforcement learning for adaptive real-time decision-making
- Full-scale deployment in active mining environments
- Integration with industrial IoT platforms
- Multi-agent coordination for fleets of autonomous mining vehicles

---

## 👨‍💻 Author

Gracey Dugar

Sophomore Data Science Student  
[GitHub](https://github.com/GraceyDugar) • [LinkedIn](https://www.linkedin.com/in/gracey-dugar?utm_source=share&utm_campaign=share_via&utm_content=profile&utm_medium=android_app) • [Live Demo](https://minesafe-ai.vercel.app)

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

> *"Making underground mining safer, smarter, and autonomous — one sensor at a time."*
