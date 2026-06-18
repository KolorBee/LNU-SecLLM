from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_desktop_app_stubs() -> None:
    class _DummySignalInstance:
        def connect(self, *_args, **_kwargs) -> None:
            return None

        def emit(self, *_args, **_kwargs) -> None:
            return None

    class _DummySignal:
        def __call__(self, *_args, **_kwargs):
            return _DummySignalInstance()

    class _DummyBase:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.Qt = types.SimpleNamespace(
        AlignmentFlag=types.SimpleNamespace(AlignLeft=0, AlignVCenter=0),
        HighDpiScaleFactorRoundingPolicy=types.SimpleNamespace(PassThrough=0),
    )
    qtcore.QTimer = type(
        "QTimer",
        (_DummyBase,),
        {"singleShot": staticmethod(lambda *_args, **_kwargs: None)},
    )
    qtcore.Signal = _DummySignal()
    qtcore.QObject = _DummyBase
    qtcore.QUrl = _DummyBase

    qtgui = types.ModuleType("PySide6.QtGui")
    for name in (
        "QColor",
        "QIcon",
        "QPainter",
        "QPixmap",
        "QAction",
        "QDesktopServices",
        "QFont",
    ):
        setattr(qtgui, name, _DummyBase)

    qtwidgets = types.ModuleType("PySide6.QtWidgets")
    for name in (
        "QApplication",
        "QMainWindow",
        "QWidget",
        "QFrame",
        "QLabel",
        "QLineEdit",
        "QPushButton",
        "QComboBox",
        "QVBoxLayout",
        "QHBoxLayout",
        "QGridLayout",
        "QFormLayout",
        "QScrollArea",
        "QStackedWidget",
        "QListWidget",
        "QListWidgetItem",
        "QPlainTextEdit",
        "QFileDialog",
        "QDialog",
        "QDialogButtonBox",
        "QButtonGroup",
        "QRadioButton",
        "QToolButton",
        "QSystemTrayIcon",
        "QMenu",
        "QSizePolicy",
        "QSplitter",
    ):
        setattr(qtwidgets, name, _DummyBase)
    qtwidgets.QSystemTrayIcon = type(
        "QSystemTrayIcon",
        (_DummyBase,),
        {"ActivationReason": types.SimpleNamespace(DoubleClick=1)},
    )
    qtwidgets.QSizePolicy = type(
        "QSizePolicy",
        (_DummyBase,),
        {"Policy": types.SimpleNamespace(Fixed=0, Expanding=0)},
    )

    pyside6 = types.ModuleType("PySide6")
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = qtcore
    sys.modules["PySide6.QtGui"] = qtgui
    sys.modules["PySide6.QtWidgets"] = qtwidgets

    qmt_agent_stub = types.ModuleType("qmt_agent")
    qmt_agent_stub.AgentConfig = type("AgentConfig", (), {})
    qmt_agent_stub.AuthManager = type("AuthManager", (), {})
    qmt_agent_stub.QMTAgent = type("QMTAgent", (), {})
    qmt_agent_stub.QMTClient = type("QMTClient", (), {})
    qmt_agent_stub.normalize_agent_config_data = lambda data: data
    qmt_agent_stub.validate_config_dict = lambda _data: []
    sys.modules["qmt_agent"] = qmt_agent_stub


def _load_desktop_app_module():
    _install_desktop_app_stubs()
    sys.modules.pop("tools.qmt_agent.desktop_app", None)
    return importlib.import_module("tools.qmt_agent.desktop_app")


def test_handoff_visible_instance_opens_gui(monkeypatch) -> None:
    desktop_app = _load_desktop_app_module()
    called = []

    monkeypatch.setattr(
        desktop_app,
        "_call_local_api",
        lambda path: called.append(path) or True,
    )

    assert (
        desktop_app._handoff_to_existing_instance(start_hidden=False) is True
    )
    assert called == ["/open_gui"]


def test_handoff_hidden_instance_checks_status(monkeypatch) -> None:
    desktop_app = _load_desktop_app_module()
    called = []

    monkeypatch.setattr(
        desktop_app,
        "_call_local_api",
        lambda path: called.append(path) or True,
    )

    assert desktop_app._handoff_to_existing_instance(start_hidden=True) is True
    assert called == ["/status"]


def test_cleanup_legacy_autostart_artifacts_calls_both_cleanup_paths(
    monkeypatch,
) -> None:
    desktop_app = _load_desktop_app_module()
    called = []

    monkeypatch.setattr(desktop_app.os, "name", "nt")
    monkeypatch.setattr(
        desktop_app,
        "_remove_legacy_task_scheduler_autostart",
        lambda: called.append("task") or True,
    )
    monkeypatch.setattr(
        desktop_app,
        "_remove_legacy_registry_autostart",
        lambda: called.append("registry") or True,
    )

    desktop_app._cleanup_legacy_autostart_artifacts()

    assert called == ["task", "registry"]


def test_cleanup_legacy_autostart_artifacts_noops_on_non_windows(
    monkeypatch,
) -> None:
    desktop_app = _load_desktop_app_module()
    called = []

    monkeypatch.setattr(desktop_app.os, "name", "posix")
    monkeypatch.setattr(
        desktop_app,
        "_remove_legacy_task_scheduler_autostart",
        lambda: called.append("task") or True,
    )
    monkeypatch.setattr(
        desktop_app,
        "_remove_legacy_registry_autostart",
        lambda: called.append("registry") or True,
    )

    desktop_app._cleanup_legacy_autostart_artifacts()

    assert called == []


def test_cleanup_cache_restores_previous_running_state(monkeypatch, tmp_path) -> None:
    desktop_app = _load_desktop_app_module()
    runtime = desktop_app.DesktopRuntime()
    qmt_path = tmp_path / "userdata_mini"
    qmt_path.mkdir()
    (qmt_path / "queue_test_mutex").write_text("x", encoding="utf-8")
    (qmt_path / "down_queue_176943234").write_text("x", encoding="utf-8")
    (qmt_path / "miniqmtShmQuoteCache").write_text("x", encoding="utf-8")
    (qmt_path / "keep_me.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        desktop_app,
        "build_agent_config",
        lambda _data: types.SimpleNamespace(qmt_path=str(qmt_path)),
    )

    stop_calls = []
    start_calls = []
    monkeypatch.setattr(runtime, "_is_running", lambda: True)
    monkeypatch.setattr(runtime, "stop", lambda: stop_calls.append(True) or {"ok": True, "message": "stopped"})
    monkeypatch.setattr(runtime, "start", lambda data: start_calls.append(data) or {"ok": True, "message": "started"})
    monkeypatch.setattr(desktop_app.time, "sleep", lambda *_args, **_kwargs: None)

    result = runtime.cleanup_cache({"qmt_path": str(qmt_path)})

    assert result["ok"] is True
    assert result["was_running"] is True
    assert "恢复 Agent 运行" in result["message"]
    assert stop_calls == [True]
    assert len(start_calls) == 1
    assert not (qmt_path / "queue_test_mutex").exists()
    assert not (qmt_path / "down_queue_176943234").exists()
    assert not (qmt_path / "miniqmtShmQuoteCache").exists()
    assert (qmt_path / "keep_me.txt").exists()


def test_stop_and_cleanup_cache_keeps_runtime_stopped(monkeypatch, tmp_path) -> None:
    desktop_app = _load_desktop_app_module()
    runtime = desktop_app.DesktopRuntime()
    qmt_path = tmp_path / "userdata_mini"
    qmt_path.mkdir()
    (qmt_path / "queue_test_mutex").write_text("x", encoding="utf-8")
    (qmt_path / "down_queue_176943235_mutex").write_text("x", encoding="utf-8")
    (qmt_path / "miniqmtShmStockListCacheHK").write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        desktop_app,
        "build_agent_config",
        lambda _data: types.SimpleNamespace(qmt_path=str(qmt_path)),
    )

    stop_calls = []
    start_calls = []
    monkeypatch.setattr(runtime, "_is_running", lambda: True)
    monkeypatch.setattr(runtime, "stop", lambda: stop_calls.append(True) or {"ok": True, "message": "stopped"})
    monkeypatch.setattr(runtime, "start", lambda data: start_calls.append(data) or {"ok": True, "message": "started"})
    monkeypatch.setattr(desktop_app.time, "sleep", lambda *_args, **_kwargs: None)

    result = runtime.stop_and_cleanup_cache({"qmt_path": str(qmt_path)})

    assert result["ok"] is True
    assert "保持停止状态" in result["message"]
    assert stop_calls == [True]
    assert start_calls == []
    assert not (qmt_path / "queue_test_mutex").exists()
    assert not (qmt_path / "down_queue_176943235_mutex").exists()
    assert not (qmt_path / "miniqmtShmStockListCacheHK").exists()


def test_cleanup_cache_failure_attempts_to_restore_runtime(monkeypatch, tmp_path) -> None:
    desktop_app = _load_desktop_app_module()
    runtime = desktop_app.DesktopRuntime()
    qmt_path = tmp_path / "userdata_mini"
    qmt_path.mkdir()
    monkeypatch.setattr(
        desktop_app,
        "build_agent_config",
        lambda _data: types.SimpleNamespace(qmt_path=str(qmt_path)),
    )

    monkeypatch.setattr(runtime, "_is_running", lambda: True)
    monkeypatch.setattr(runtime, "stop", lambda: {"ok": True, "message": "stopped"})
    monkeypatch.setattr(runtime, "start", lambda data: {"ok": True, "message": "started"})
    monkeypatch.setattr(
        desktop_app,
        "_cleanup_qmt_temp_files",
        lambda _path: {"scanned": 1, "removed": 0, "failed": 1, "removed_files": [], "failed_files": [{"name": "queue_test_mutex", "error": "busy"}]},
    )
    monkeypatch.setattr(desktop_app.time, "sleep", lambda *_args, **_kwargs: None)

    result = runtime.cleanup_cache({"qmt_path": str(qmt_path)})

    assert result["ok"] is False
    assert "Agent 已恢复运行" in result["message"]
    assert result["restore"]["ok"] is True
