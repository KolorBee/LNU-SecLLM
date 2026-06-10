# GitHub Publish Checklist

This project is not ready to publish until the items below are handled.

## 1. License And Attribution

Do not hide that this project integrates upstream work. If upstream licenses require attribution, redistribution terms,
or source notices, those requirements must be kept.

Before publishing:

```bash
find src -iname '*license*' -o -iname 'copying*' -o -iname 'notice*'
```

Then:

- Keep `src/HesaiLidar_ROS_2.0/LICENSE`.
- Add or clarify licenses for packages that still say `TODO`.
- Keep a top-level `THIRD_PARTY_NOTICES.md`.
- Decide your own top-level project license only after confirming it is compatible with bundled upstream code.

## 2. Remove Private Or Machine-Specific Data

Do not commit:

- `build/`, `install/`, `log/`
- `.ros/`, `~/.ros/rtabmap.db`
- saved maps unless they are intentionally public demo maps
- rosbag/mcap files
- private IPs, credentials, SSH keys, tokens

The current `.gitignore` already excludes common generated files and maps.

## 3. Make Paths Portable

After cloning on another machine:

```bash
./scripts/configure_hesai_paths.sh
./scripts/build.sh
```

`unitree_ros2` is intentionally external and must be installed/sourced separately.

## 4. Initialize Git Locally

When ready:

```bash
cd /home/star/unitree-go2-fan
git init
git add README.md THIRD_PARTY_NOTICES.md docs scripts src .gitignore maps/.gitkeep
git status
git commit -m "Initial unitree-go2-fan integration"
```

## 5. Create The GitHub Repository

On GitHub, create an empty repository named `unitree-go2-fan`, without adding README/LICENSE/gitignore online.

Then:

```bash
git branch -M main
git remote add origin git@github.com:<your-user>/unitree-go2-fan.git
git push -u origin main
```

## 6. Optional Future Cleanup

For a cleaner public release, consider:

- Renaming local packages from `go2_slam_nav` to a project-specific package name.
- Replacing vendored third-party code with Git submodules or documented dependency install steps.
- Moving robot/site-specific launch defaults into example config files.
- Adding screenshots, architecture diagrams, and tested hardware versions.
