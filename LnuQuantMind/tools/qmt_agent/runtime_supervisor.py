"""Shared supervised runtime loop for CLI and desktop host."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
import time
from typing import Callable, Generic, Optional, TypeVar


AgentT = TypeVar("AgentT")


@dataclass(frozen=True)
class RestartPolicy:
    auto_restart_on_crash: bool = True
    restart_base_delay_seconds: int = 3
    restart_max_delay_seconds: int = 60
    restart_window_seconds: int = 600
    restart_max_attempts_per_window: int = 20


class RuntimeSupervisor(Generic[AgentT]):
    def __init__(
        self,
        *,
        agent_factory: Callable[[], AgentT],
        stop_event: threading.Event,
        policy: RestartPolicy,
        logger: logging.Logger,
        service_name: str,
        should_run: Optional[Callable[[], bool]] = None,
        on_agent_created: Optional[Callable[[AgentT], None]] = None,
        on_agent_cleared: Optional[Callable[[AgentT], None]] = None,
        on_run_failure: Optional[Callable[[str], None]] = None,
        on_restart_scheduled: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        self.agent_factory = agent_factory
        self.stop_event = stop_event
        self.policy = policy
        self.logger = logger
        self.service_name = service_name
        self.should_run = should_run or (lambda: not self.stop_event.is_set())
        self.on_agent_created = on_agent_created or (lambda _agent: None)
        self.on_agent_cleared = on_agent_cleared or (lambda _agent: None)
        self.on_run_failure = on_run_failure or (lambda _message: None)
        self.on_restart_scheduled = on_restart_scheduled or (lambda _reason, _delay, _run_seconds: None)

    def _wait_or_stop(self, seconds: int) -> bool:
        deadline = time.time() + max(0, int(seconds))
        while time.time() < deadline:
            if self.stop_event.is_set() or not self.should_run():
                return True
            time.sleep(0.2)
        return self.stop_event.is_set() or not self.should_run()

    def run(self) -> int:
        restart_marks: list[float] = []
        while not self.stop_event.is_set() and self.should_run():
            agent = self.agent_factory()
            self.on_agent_created(agent)
            run_started_at = time.time()
            exit_reason: str | None = None
            crashed = False
            try:
                getattr(agent, "run_forever")(external_stop_event=self.stop_event)
                if not self.stop_event.is_set() and self.should_run():
                    if getattr(agent, "stop_event").is_set():
                        exit_reason = "agent stop_event set unexpectedly"
                    else:
                        exit_reason = "agent 主循环意外退出"
            except Exception as exc:
                if self.stop_event.is_set() or not self.should_run():
                    break
                crashed = True
                exit_reason = str(exc)
                self.logger.exception("%s crashed, will evaluate restart policy", self.service_name)
                self.on_run_failure(exit_reason)
            finally:
                try:
                    getattr(agent, "stop")()
                except Exception:
                    self.logger.exception("%s stop failed during supervisor cleanup", self.service_name)
                self.on_agent_cleared(agent)

            if self.stop_event.is_set() or not self.should_run():
                break
            if not exit_reason:
                break

            if not self.policy.auto_restart_on_crash:
                self.logger.error("%s exited and auto-restart is disabled: %s", self.service_name, exit_reason)
                return 1

            now = time.time()
            restart_marks = [ts for ts in restart_marks if now - ts <= self.policy.restart_window_seconds]
            attempt = len(restart_marks) + 1
            if attempt > self.policy.restart_max_attempts_per_window:
                self.logger.error(
                    "%s restart attempts exceeded window limit (%s in %ss), last_error=%s",
                    self.service_name,
                    self.policy.restart_max_attempts_per_window,
                    self.policy.restart_window_seconds,
                    exit_reason,
                )
                return 1

            restart_marks.append(now)
            run_duration = max(0, int(now - run_started_at))
            restart_delay = min(
                self.policy.restart_max_delay_seconds,
                self.policy.restart_base_delay_seconds * (2 ** (attempt - 1)),
            )
            if crashed:
                self.on_run_failure(exit_reason)
            self.on_restart_scheduled(exit_reason, restart_delay, run_duration)
            self.logger.warning(
                "%s exited unexpectedly after %ss (attempt %s/%s), restarting in %ss, reason=%s",
                self.service_name,
                run_duration,
                attempt,
                self.policy.restart_max_attempts_per_window,
                restart_delay,
                exit_reason,
            )
            if self._wait_or_stop(restart_delay):
                break
        return 0
