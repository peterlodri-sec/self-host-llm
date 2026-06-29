# SPDX-License-Identifier: MIT
"""Resource manager: memory, CPU monitoring + graceful throttling."""

import os
import time
from typing import Optional

import psutil

from ultrawhale.config import Config
from ultrawhale.logging import get_logger

logger = get_logger("resources")
cfg = Config()


class ResourceManager:
    """Monitor and manage system resources."""

    def __init__(
        self,
        max_memory_percent: Optional[float] = None,
        max_cpu_percent: Optional[float] = None,
    ):
        """Initialize with resource limits (% of system total).

        Args:
            max_memory_percent: Memory threshold. Falls back to
                ``Config.max_memory_percent`` (default 50).
            max_cpu_percent: CPU threshold. Falls back to
                ``Config.max_cpu_percent`` (default 75).
        """
        self.max_memory_percent = (
            max_memory_percent if max_memory_percent is not None else cfg.max_memory_percent
        )
        self.max_cpu_percent = (
            max_cpu_percent if max_cpu_percent is not None else cfg.max_cpu_percent
        )
        self.pause_flag: bool = False

    def check_memory(self) -> bool:
        """Check if memory usage is within limits."""
        try:
            mem = psutil.virtual_memory()
            if mem.percent > self.max_memory_percent:
                logger.warning(
                    "Memory high: %.1f%% > %s%%",
                    mem.percent,
                    self.max_memory_percent,
                )
                return False
            return True
        except Exception as e:
            logger.error("Memory check error: %s", e)
            return True

    def check_cpu(self) -> bool:
        """Check if CPU load is within limits."""
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            if cpu > self.max_cpu_percent:
                logger.warning(
                    "CPU high: %.1f%% > %s%%",
                    cpu,
                    self.max_cpu_percent,
                )
                return False
            return True
        except Exception as e:
            logger.error("CPU check error: %s", e)
            return True

    def is_system_healthy(self) -> bool:
        """Check if system resources are healthy."""
        return self.check_memory() and self.check_cpu()

    def wait_for_resources(self, max_wait: int = 300) -> bool:
        """Block until resources are available (up to *max_wait* seconds).

        Args:
            max_wait: Maximum seconds to wait (default 300 / 5 min).

        Returns:
            True if resources became available within the window.
        """
        start = time.time()
        while time.time() - start < max_wait:
            if self.is_system_healthy() and not self.pause_flag:
                return True
            elapsed = int(time.time() - start)
            logger.info("Throttling — waiting for resources… (%ss/%ss)", elapsed, max_wait)
            time.sleep(10)
        return False

    def pause(self) -> None:
        """Pause generation."""
        self.pause_flag = True
        logger.info("Generation paused")

    def resume(self) -> None:
        """Resume generation."""
        self.pause_flag = False
        logger.info("Generation resumed")

    def get_status(self) -> dict:
        """Get current resource status as a dictionary."""
        try:
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.1)
            return {
                "memory_percent": mem.percent,
                "memory_available_gb": mem.available / (1024**3),
                "cpu_percent": cpu,
                "paused": self.pause_flag,
                "healthy": self.is_system_healthy(),
            }
        except Exception as e:
            logger.error("Status check error: %s", e)
            return {"error": str(e)}


class ProcessManager:
    """Manage worker processes with resource limits."""

    def __init__(self, resource_manager: ResourceManager):
        self.rm: ResourceManager = resource_manager
        self.processes: dict[int, psutil.Popen] = {}
        self.dead_workers: set[int] = set()

    def launch_process(
        self, worker_id: int, cmd: list[str], log_file: str
    ) -> Optional[psutil.Popen]:
        """Launch a worker process with resource monitoring.

        Args:
            worker_id: Numeric worker identifier.
            cmd: Command and arguments to execute.
            log_file: Path to redirect stdout/stderr.

        Returns:
            The :class:`psutil.Popen` handle, or ``None`` on failure.
        """
        try:
            with open(log_file, "w") as log_f:
                proc = psutil.Popen(
                    cmd,
                    stdout=log_f,
                    stderr=log_f,
                    preexec_fn=os.setsid if hasattr(os, "setsid") else None,
                )

            # Try to set memory limit (macOS may not support)
            try:
                _ = psutil.Process(proc.pid)
                # Note: memory limits require elevated permissions on macOS
                # Just monitor instead
            except Exception as e:
                logger.warning("Could not inspect process limits: %s", e)

            self.processes[worker_id] = proc
            logger.info(
                "Worker %s launched (PID %s)", worker_id, proc.pid
            )
            return proc

        except Exception as e:
            logger.error("Failed to launch worker %s: %s", worker_id, e)
            self.dead_workers.add(worker_id)
            return None

    def monitor_process(self, worker_id: int) -> bool:
        """Check if a worker process is still alive.

        Args:
            worker_id: Numeric worker identifier.

        Returns:
            ``True`` if the process is running.
        """
        if worker_id not in self.processes:
            return False
        proc = self.processes[worker_id]
        return proc.poll() is None

    def kill_process(self, worker_id: int, force: bool = False) -> None:
        """Gracefully (or forcefully) terminate a worker process.

        Args:
            worker_id: Numeric worker identifier.
            force: If ``True``, kill immediately instead of
                ``terminate`` + wait + fallback.
        """
        if worker_id not in self.processes:
            return
        proc = self.processes[worker_id]
        try:
            if force:
                proc.kill()
                logger.info("Worker %s force-killed", worker_id)
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except psutil.TimeoutExpired:
                    proc.kill()
                logger.info("Worker %s terminated", worker_id)
        except Exception as e:
            logger.warning("Error killing worker %s: %s", worker_id, e)

    def cleanup_all(self) -> None:
        """Terminate all tracked worker processes."""
        for worker_id in list(self.processes.keys()):
            if self.monitor_process(worker_id):
                self.kill_process(worker_id, force=False)

    def get_process_stats(self) -> dict:
        """Return aggregate statistics for all tracked processes.

        Returns:
            Dictionary with keys ``alive``, ``dead``, and
            ``memory_mb``.
        """
        stats: dict[str, float | int] = {"alive": 0, "dead": 0, "memory_mb": 0}
        for worker_id, proc in self.processes.items():
            if self.monitor_process(worker_id):
                stats["alive"] += 1  # type: ignore[operator]
                try:
                    p = psutil.Process(proc.pid)
                    stats["memory_mb"] += p.memory_info().rss / (1024**2)  # type: ignore[operator]
                except Exception:
                    logger.warning(
                        "Could not read memory for worker %s", worker_id
                    )
            else:
                stats["dead"] += 1  # type: ignore[operator]
        return stats
