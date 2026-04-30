from __future__ import annotations

import colorsys
import json
import logging
from pathlib import Path
from uuid import uuid4

import numpy
import spectral
from flask import Flask, jsonify, request, send_from_directory
from PIL import Image
from werkzeug.utils import secure_filename

from pycoal.mineral import MineralClassification
from pycoal.mining import MiningClassification


WEB_ROOT = Path(__file__).resolve().parent
REPO_ROOT = WEB_ROOT.parent
RUNS_DIR = WEB_ROOT / "runs"
RUNS_DIR.mkdir(exist_ok=True)

DEFAULTS = {
    "mineral": {
        "image_path": "pycoal/tests/images/ang20140912t192359_corr_v1c_img_400-410_10-20.hdr",
        "library_path": "pycoal/tests/s06av95a_envi.hdr",
        "config_path": "pycoal/tests/test_config_files/config_test.ini",
    },
    "mining": {
        "image_path": "pycoal/tests/images/ang20150420t182808_corr_v1e_img_class_4200-4210_70-80.hdr",
        "spectral_version": "7",
    },
}


app = Flask(__name__, static_folder=str(WEB_ROOT), static_url_path="")
logging.basicConfig(level=logging.INFO)


def resolve_repo_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"Path not found: {candidate}")
    return candidate


def save_uploaded_file(upload_dir: Path, storage, fallback_name: str | None = None) -> Path:
    filename = secure_filename(storage.filename or fallback_name or "upload.bin")
    destination = upload_dir / filename
    storage.save(destination)
    return destination


def uploaded_or_default_path(upload_dir: Path, form, files, basename: str, default_path: str | None = None) -> Path:
    path_value = (form.get(f"{basename}_path") or "").strip()
    if path_value:
        return resolve_repo_path(path_value)

    hdr_file = files.get(f"{basename}_hdr")
    img_file = files.get(f"{basename}_img")
    if hdr_file is not None:
        hdr_path = save_uploaded_file(upload_dir, hdr_file, f"{basename}.hdr")
        if img_file is not None:
            save_uploaded_file(upload_dir, img_file, hdr_path.with_suffix(".img").name)
        else:
            raise FileNotFoundError(f"Missing .img pair for uploaded {basename} dataset.")
        return hdr_path

    if default_path is None:
        raise FileNotFoundError(f"No input provided for {basename} dataset.")
    return resolve_repo_path(default_path)


def uploaded_or_default_config(upload_dir: Path, form, files, default_path: str) -> Path:
    config_path = (form.get("config_path") or "").strip()
    if config_path:
        return resolve_repo_path(config_path)

    config_file = files.get("config_file")
    if config_file is not None:
        return save_uploaded_file(upload_dir, config_file, "config.ini")
    return resolve_repo_path(default_path)


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path.relative_to(WEB_ROOT))


def normalize_rgb(array: numpy.ndarray) -> numpy.ndarray:
    rgb = numpy.array(array, dtype=numpy.float64, copy=True)
    if rgb.ndim == 2:
        rgb = rgb[:, :, numpy.newaxis]
    if rgb.shape[2] == 1:
        rgb = numpy.repeat(rgb, 3, axis=2)

    output = numpy.zeros_like(rgb, dtype=numpy.uint8)
    for index in range(min(3, rgb.shape[2])):
        channel = rgb[:, :, index]
        channel = numpy.nan_to_num(channel, nan=0.0, posinf=0.0, neginf=0.0)
        low = numpy.percentile(channel, 2)
        high = numpy.percentile(channel, 98)
        if high <= low:
            scaled = numpy.zeros_like(channel, dtype=numpy.uint8)
        else:
            scaled = numpy.clip((channel - low) / (high - low), 0, 1)
            scaled = (scaled * 255).astype(numpy.uint8)
        output[:, :, index] = scaled

    return output[:, :, :3]


def palette_for_classes(class_count: int) -> list[tuple[int, int, int]]:
    palette = [(0, 0, 0)]
    for index in range(1, max(class_count, 2)):
        hue = ((index - 1) * 0.61803398875) % 1.0
        red, green, blue = colorsys.hsv_to_rgb(hue, 0.65, 0.96)
        palette.append((int(red * 255), int(green * 255), int(blue * 255)))
    return palette


def classification_to_rgb(array: numpy.ndarray) -> numpy.ndarray:
    classes = numpy.array(array[:, :, 0], dtype=numpy.int32)
    palette = palette_for_classes(int(classes.max()) + 1)
    colored = numpy.zeros((classes.shape[0], classes.shape[1], 3), dtype=numpy.uint8)
    for class_index, color in enumerate(palette):
        colored[classes == class_index] = color
    return colored


def export_png_from_envi(image_path: Path, png_path: Path, classification: bool = False) -> None:
    envi_image = spectral.open_image(str(image_path))
    data = envi_image.asarray()
    if classification:
        rgb = classification_to_rgb(data)
    else:
        rgb = normalize_rgb(data)
    Image.fromarray(rgb, mode="RGB").save(png_path)


def run_mineral(payload: dict, run_dir: Path) -> dict:
    image_path = resolve_repo_path(payload.get("image_path") or DEFAULTS["mineral"]["image_path"])
    library_path = resolve_repo_path(payload.get("library_path") or DEFAULTS["mineral"]["library_path"])
    config_path = resolve_repo_path(payload.get("config_path") or DEFAULTS["mineral"]["config_path"])

    rgb_hdr = run_dir / "source_rgb.hdr"
    class_hdr = run_dir / "mineral_classified.hdr"
    source_png = run_dir / "source_preview.png"
    result_png = run_dir / "result_preview.png"

    MineralClassification.to_rgb(str(image_path), str(rgb_hdr))
    classifier = MineralClassification(library_file_name=str(library_path), config_file=str(config_path))
    classifier.classify_image(str(image_path), str(class_hdr))

    export_png_from_envi(rgb_hdr, source_png)
    export_png_from_envi(class_hdr, result_png, classification=True)

    return {
        "workflow": "mineral",
        "input_path": display_path(image_path),
        "result_path": display_path(class_hdr),
        "source_preview_url": f"/runs/{run_dir.name}/source_preview.png",
        "result_preview_url": f"/runs/{run_dir.name}/result_preview.png",
    }


def run_mining(payload: dict, run_dir: Path) -> dict:
    image_path = resolve_repo_path(payload.get("image_path") or DEFAULTS["mining"]["image_path"])
    spectral_version = str(payload.get("spectral_version") or DEFAULTS["mining"]["spectral_version"])

    result_hdr = run_dir / "mining_classified.hdr"
    source_png = run_dir / "source_preview.png"
    result_png = run_dir / "result_preview.png"

    classifier = MiningClassification()
    classifier.classify_image(str(image_path), str(result_hdr), spectral_version)

    export_png_from_envi(image_path, source_png, classification=True)
    export_png_from_envi(result_hdr, result_png, classification=True)

    return {
        "workflow": "mining",
        "input_path": display_path(image_path),
        "result_path": display_path(result_hdr),
        "source_preview_url": f"/runs/{run_dir.name}/source_preview.png",
        "result_preview_url": f"/runs/{run_dir.name}/result_preview.png",
    }


def run_mineral_upload(form, files, run_dir: Path) -> dict:
    upload_dir = run_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    image_path = uploaded_or_default_path(upload_dir, form, files, "image", DEFAULTS["mineral"]["image_path"])
    library_path = uploaded_or_default_path(upload_dir, form, files, "library", DEFAULTS["mineral"]["library_path"])
    config_path = uploaded_or_default_config(upload_dir, form, files, DEFAULTS["mineral"]["config_path"])

    payload = {
        "image_path": str(image_path),
        "library_path": str(library_path),
        "config_path": str(config_path),
    }
    return run_mineral(payload, run_dir)


def run_mining_upload(form, files, run_dir: Path) -> dict:
    upload_dir = run_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    image_path = uploaded_or_default_path(upload_dir, form, files, "image", DEFAULTS["mining"]["image_path"])
    payload = {
        "image_path": str(image_path),
        "spectral_version": str(form.get("spectral_version") or DEFAULTS["mining"]["spectral_version"]),
    }
    return run_mining(payload, run_dir)


@app.get("/")
def index() -> object:
    return send_from_directory(WEB_ROOT, "index.html")


@app.get("/api/defaults")
def defaults() -> object:
    return jsonify(DEFAULTS)


@app.post("/api/run")
def run_pipeline() -> object:
    payload = request.get_json(force=True, silent=False)
    workflow = payload.get("workflow", "mineral")
    run_dir = RUNS_DIR / uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        if workflow == "mineral":
            result = run_mineral(payload, run_dir)
        elif workflow == "mining":
            result = run_mining(payload, run_dir)
        else:
            raise ValueError("Unsupported workflow. Use 'mineral' or 'mining'.")
        metadata_path = run_dir / "metadata.json"
        metadata_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return jsonify({"ok": True, **result})
    except Exception as exc:
        logging.exception("Pipeline run failed")
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/run-upload")
def run_upload_pipeline() -> object:
    workflow = request.form.get("workflow", "mineral")
    run_dir = RUNS_DIR / uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        if workflow == "mineral":
            result = run_mineral_upload(request.form, request.files, run_dir)
        elif workflow == "mining":
            result = run_mining_upload(request.form, request.files, run_dir)
        else:
            raise ValueError("Unsupported workflow. Use 'mineral' or 'mining'.")
        metadata_path = run_dir / "metadata.json"
        metadata_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return jsonify({"ok": True, **result})
    except Exception as exc:
        logging.exception("Upload pipeline run failed")
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/runs/<run_id>/<path:filename>")
def serve_run_artifact(run_id: str, filename: str) -> object:
    return send_from_directory(RUNS_DIR / run_id, filename)


if __name__ == "__main__":
    app.run(debug=True, port=8000)