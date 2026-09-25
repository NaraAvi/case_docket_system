import os
import threading


class SLAThreadScheduler:
    """Minimal background scheduler for the Flask prototype.

    This intentionally reuses the app's registered automation callback instead of
    duplicating SLA logic in a second code path. Each tick triggers the existing
    automation job registry, which calls the authoritative enforcement flow.
    """

    def __init__(self, app, interval_seconds: int = 60):
        self.app = app
        self.interval_seconds = max(1, int(interval_seconds))
        self._stop_event = threading.Event()
        self._thread = None
        self._lock = threading.Lock()

    def run_once(self):
        if self.app is None:
            return None

        try:
            with self.app.app_context():
                automation_service = self.app.extensions.get("automation_service")
                if automation_service is None:
                    return None
                try:
                    return automation_service.trigger_registered_jobs()
                except Exception:
                    self.app.logger.exception("SLA scheduler tick failed")
                    return None
        except Exception:
            self.app.logger.exception("SLA scheduler context setup failed")
            return None

    def _loop(self):
        while not self._stop_event.is_set():
            self.run_once()
            self._stop_event.wait(self.interval_seconds)

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self
            if self.app is not None and getattr(self.app, "testing", False):
                return self

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, name="sla-background-scheduler", daemon=True)
            self._thread.start()
            return self

    def shutdown(self):
        with self._lock:
            self._stop_event.set()
            thread = self._thread
            self._thread = None

        if thread is not None and thread.is_alive():
            thread.join(timeout=self.interval_seconds + 2)

        return None


def _is_reloader_parent():
    return os.environ.get("WERKZEUG_RUN_MAIN") != "true"


def start_sla_scheduler(app, interval_seconds: int = 60):
    """Start a single SLA scheduler for this Flask app.

    The scheduler is intentionally minimal and uses the existing automation job
    registry so the enforcement logic remains centralized in AutomationService.
    """
    if app is None:
        return None

    app_extensions = getattr(app, "extensions", None)
    if app_extensions is None:
        return None

    if app.debug and _is_reloader_parent():
        return None

    existing = app_extensions.get("sla_scheduler")
    if existing is not None:
        if getattr(existing, "app", None) is app:
            if getattr(existing, "_thread", None) is not None and existing._thread.is_alive():
                return existing
            if app.config.get("TESTING"):
                return existing
            existing.start()
            app_extensions["sla_scheduler"] = existing
            return existing
        app_extensions["sla_scheduler"] = None

    scheduler = SLAThreadScheduler(app, interval_seconds=interval_seconds)
    if app.config.get("TESTING"):
        app_extensions["sla_scheduler"] = scheduler
        return scheduler

    scheduler.start()
    app_extensions["sla_scheduler"] = scheduler
    return scheduler


def shutdown_sla_scheduler(app):
    if app is None:
        return None

    scheduler = getattr(app, "extensions", {}).get("sla_scheduler")
    if scheduler is not None:
        scheduler.shutdown()
        app.extensions["sla_scheduler"] = None
    return None
