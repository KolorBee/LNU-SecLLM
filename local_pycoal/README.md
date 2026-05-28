# Pycoal

English | 中文

Pycoal is a Python toolkit for hyperspectral remote sensing workflows focused on mineral identification, mining proxy detection, and environmental correlation analysis from AVIRIS and similar spectral imagery.

Pycoal 是一个面向高光谱遥感场景的 Python 工具集，主要用于 AVIRIS 及类似光谱影像的矿物识别、采矿代理分类和环境相关性分析。

## What This Project Does | 项目用途

English:

- Mineral classification from hyperspectral images using spectral libraries.
- Mining classification by mapping mineral classes to mining proxy classes.
- Environmental correlation by intersecting mining outputs with vector features such as hydrography.
- Command-line entry points for running the workflows from scripts or terminals.

中文：

- 使用光谱库对高光谱影像进行矿物分类。
- 将矿物分类结果映射为采矿代理类别，生成采矿分类结果。
- 将采矿结果与河流等矢量要素进行空间关联，生成环境相关性结果。
- 提供命令行入口，便于脚本化运行和批处理。

## Main Modules | 核心模块

English:

- `pycoal.mineral`: mineral classification, RGB export, SAM-based workflows.
- `pycoal.mining`: mining proxy classification from mineral classification outputs.
- `pycoal.environment`: environmental correlation using GDAL command-line tools.
- `pycoal.cli.*`: CLI wrappers for the three workflows.

中文：

- `pycoal.mineral`：矿物分类、RGB 导出、基于 SAM 的分类流程。
- `pycoal.mining`：基于矿物分类结果的采矿代理分类。
- `pycoal.environment`：借助 GDAL 命令行工具进行环境相关分析。
- `pycoal.cli.*`：三类工作流对应的命令行封装。

## Current Repository Status | 当前仓库状态

English:

- Core Python environment has been configured in `.venv`.
- `pycoal-mineral` and `pycoal-mining` run successfully with bundled test data.
- `pycoal-environment` still requires system GDAL tools on `PATH`, specifically `gdal_rasterize` and `gdal_proximity.py`.
- Legacy `nose` tests are not compatible with Python 3.13 because `nose` depends on the removed standard library module `imp`.

中文：

- 已在仓库内配置好 `.venv` Python 虚拟环境。
- `pycoal-mineral` 和 `pycoal-mining` 已用仓库自带测试数据成功运行。
- `pycoal-environment` 仍依赖系统级 GDAL 命令行工具，至少需要 `gdal_rasterize` 和 `gdal_proximity.py` 在 `PATH` 中可用。
- 仓库原有 `nose` 测试在 Python 3.13 下不兼容，因为 `nose` 依赖已移除的标准库模块 `imp`。

## What Was Changed | 本次修改内容

English:

- Fixed a Windows-specific issue in `pycoal.mineral.MineralClassification.filter_classes`.
- The original code reopened an ENVI classification file and then overwrote the same path while the file handle was still active.
- The fix copies the image data and metadata into memory, releases the open dataset, and then saves the filtered classification back to disk.
- This change allows mineral classification to complete successfully on Windows in the current environment.

中文：

- 修复了 `pycoal.mineral.MineralClassification.filter_classes` 在 Windows 下的一个问题。
- 原始实现会重新打开 ENVI 分类文件，并在文件句柄仍被占用时覆盖写回同一路径。
- 修复方式是先把影像数据和元数据复制到内存中，释放已打开的数据集，再写回过滤后的分类结果。
- 这个改动使当前环境下的矿物分类流程可以在 Windows 上正常完成。

## Installation | 安装说明

### Recommended Environment | 推荐环境

English:

- Python 3.13 currently works for the core runtime.
- Use a virtual environment.
- Install the package in editable mode for development.

中文：

- 当前核心运行链路可在 Python 3.13 下工作。
- 建议使用虚拟环境。
- 开发场景建议使用 editable 模式安装。

### Setup Commands | 安装命令

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e . --no-deps
python -m pip install numpy spectral joblib psutil torch tqdm guzzle_sphinx_theme
```

English:

- `--no-deps` is used here because the original dependency list includes legacy or platform-heavy packages that are not required for the core workflows tested in this repository.

中文：

- 这里使用 `--no-deps`，是因为原始依赖列表中包含一些较旧或平台负担较重的包，而当前仓库已验证的核心流程并不需要全部依赖。

## GDAL Requirement For Environment Workflow | 环境分析流程的 GDAL 依赖

English:

The environment workflow depends on external GDAL command-line tools, not only Python packages. You need these commands available in your shell:

- `gdal_rasterize`
- `gdal_proximity.py`

Without them, `pycoal-environment` will fail with a `FileNotFoundError`.

中文：

环境分析流程依赖外部 GDAL 命令行工具，而不仅仅是 Python 包。你的终端环境中至少需要以下命令可用：

- `gdal_rasterize`
- `gdal_proximity.py`

如果缺少这些命令，`pycoal-environment` 会直接报 `FileNotFoundError`。

## Usage | 使用方式

### Mineral Classification | 矿物分类

```powershell
pycoal-mineral \
  -i pycoal/tests/images/ang20140912t192359_corr_v1c_img_400-410_10-20.hdr \
  -s pycoal/tests/s06av95a_envi.hdr \
  -r pycoal/tests/images/ang20140912t192359_corr_v1c_img_400-410_10-20_rgb_run.hdr \
  -c pycoal/tests/images/ang20140912t192359_corr_v1c_img_400-410_10-20_class_run.hdr \
  -cf pycoal/tests/test_config_files/config_test.ini
```

### Mining Classification | 采矿分类

```powershell
pycoal-mining \
  -mi pycoal/tests/images/ang20150420t182808_corr_v1e_img_class_4200-4210_70-80.hdr \
  -mo pycoal/tests/images/ang20150420t182808_corr_v1e_img_class_mining_run.hdr \
  -v 7
```

### Environment Correlation | 环境相关分析

```powershell
pycoal-environment \
  -m pycoal/tests/images/ang20150420t182050_corr_v1e_img_class_mining_cut.hdr \
  -hy pycoal/tests/images/NHDFlowline_cut.shp \
  -e pycoal/tests/images/ang20150420t182050_corr_v1e_img_class_mining_cut_env_run.hdr
```

English:

- The last command requires GDAL tools on `PATH`.

中文：

- 最后一条命令要求系统已安装并配置好 GDAL 命令行工具。

## Verified Outputs In This Workspace | 当前工作区已验证输出

English:

The following outputs were generated successfully during setup and validation:

- `pycoal/tests/images/ang20140912t192359_corr_v1c_img_400-410_10-20_rgb_run.hdr`
- `pycoal/tests/images/ang20140912t192359_corr_v1c_img_400-410_10-20_class_run.hdr`
- `pycoal/tests/images/ang20150420t182808_corr_v1e_img_class_mining_run.hdr`

中文：

在本次配置和验证过程中，以下输出文件已经成功生成：

- `pycoal/tests/images/ang20140912t192359_corr_v1c_img_400-410_10-20_rgb_run.hdr`
- `pycoal/tests/images/ang20140912t192359_corr_v1c_img_400-410_10-20_class_run.hdr`
- `pycoal/tests/images/ang20150420t182808_corr_v1e_img_class_mining_run.hdr`

## Project Notes | 说明

English:

- This repository originally used `README.rst`; this `README.md` is intended to be more GitHub-friendly.
- The original codebase targets an older Python ecosystem, so some dependencies and tests need modernization for long-term maintenance.

中文：

- 这个仓库原本使用 `README.rst`，这里新增的 `README.md` 更适合直接作为 GitHub 首页展示。
- 原始代码库面向较早期的 Python 生态，部分依赖和测试体系若要长期维护，仍需要继续现代化改造。

## License | 许可证

English:

This project is distributed under the GNU General Public License v2. See `LICENSE` for details.

中文：

本项目使用 GNU General Public License v2 许可证，详细信息见 `LICENSE`。