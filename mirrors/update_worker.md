### update_worker.py - DEPS 체크/자동 업그레이드 워커
"""시작 시퀀스의 의존성 확인·수급을 담당하는 백그라운드 워커 (UpdateWorker).

- _do_check : updater.check_deps() 결과를 DEPS 이벤트로(TUI 5줄), CLI 원문을
  raw 문자열로(F12) 버스 단일 경유 전송. stale 패키지는 check_done(list)으로 반환.
- _do_upgrade: ProvisioningManager를 통해 yt-dlp/streamlink/ffmpeg/node/bgutil 일괄 수급.
  각 수급의 실제 진행 여부를 _had_action 판별해 '요약 결론' 1줄만 남긴다.
- [분리] dialogs.py에서 추출 — 대화상자 컬렉션과 워커의 수명·계층이 다르다.
- [시그널 계약] check_done(list) → main._on_update_check_done,
  upgrade_done(bool,str) → StartupCoordinator.report_upgrade.
- [v3.3.0] 로그는 raw 버스(raw_log.raw) 단일 경유 — line/full 시그널 폐기.
"""
import traceback

import chzzktube.infra.updater as updater
import chzzktube.core.raw_log as raw_log
from chzzktube.core.log_event import LogEvent
from PySide6.QtCore import QThread, Signal
from chzzktube.core.log_emitter import emit_component, emit_error_standard

# CLI 원문 캡처 대상 — (label, args). _do_check에서 updater.cli_raw로 실행된다.
_RAW_VERSION_CMDS = (
    ("ytdlp", ("--version",)),
    ("streamlink", ("--version",)),
    ("ffmpeg", ("-version",)),
    ("node", ("--version",)),
    ("npm", ("--version",)),
)


class UpdateWorker(QThread):
    check_done = Signal(list)
    upgrade_done = Signal(bool, str)
    work_tick = Signal()
    deps_failed = Signal(list)

    def __init__(self, parent=None, upgrade=False, stale_updates=None, channel='stable', check_updates=True):
        super().__init__(parent)
        self.upgrade = upgrade
        self.stale_updates = stale_updates or []
        self.channel = channel
        self.check_updates = check_updates
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            if self.upgrade:
                self._do_upgrade()
            else:
                self._do_check()
        except Exception as e:
            traceback.print_exc()
            raw_log.raw("deps", LogEvent(stage="DEPS", status="FAIL", scope="DEPS",
                                         msg=f"worker crash: {e}", is_error=True), to_tui=True)
            if self.upgrade:
                self.upgrade_done.emit(False, "worker crash")
            else:
                self.check_done.emit([])

    def _do_check(self):
        stale = []
        results = list(updater.check_deps(
            log_func=lambda m: raw_log.raw(
                "pot-readiness",
                LogEvent(stage="POT", status="RUN", scope="POT", msg=str(m)),
            )
        ))
        for label, status, ver in results:
            raw_log.raw("deps", emit_component("DEPS", status, {"ytdlp": "YTDL", "streamlink": "STRE", "ffmpeg": "FFMP", "node": "NODE", "pot": "POT"}.get(label, label), ver), to_tui=True)
        for label, args in _RAW_VERSION_CMDS:
            cmdline, out = updater.cli_raw(label, *args)
            if cmdline and out:
                raw_log.raw("deps-cli", f"$ {cmdline}", to_tui=False)
                for line in updater.truncate_for_full_log(out).splitlines():
                    raw_log.raw("deps-cli", line, to_tui=False)
        if self.check_updates:
            for label, pypi_name, cur, latest in updater.outdated_packages(channel=self.channel):
                stale.append((label, pypi_name, cur, latest))
                raw_log.raw("pypi", f"[stale] {label} {cur} -> {latest}")
        else:
            raw_log.raw("pypi", "pypi update check: disabled (auto_update_check=off)")
        self.deps_failed.emit([label for label, status, _ in results if status == "FAIL"])
        self.check_done.emit(stale)

    def _provision_cb(self, msg, is_status=False, is_error=False,
                      component_id=None, is_progress=False):
        if isinstance(msg, LogEvent):
            event = msg
            if is_status:
                event.is_status = True
            if is_error:
                event.is_error = True
        else:
            event = LogEvent(
                stage="DEPS",
                status="FAIL" if is_error else ("RUN" if is_status else "OK"),
                scope="DEPS", msg=str(msg),
                is_status=is_status, is_error=is_error,
            )
        if component_id is not None:
            event.component_id = component_id
        if is_progress:
            event.is_progress = True

        component_id = getattr(event, "component_id", component_id)
        is_progress = bool(getattr(event, "is_progress", is_progress))

        # [게이트 개방] OK와 DONE 상태를 버리지 않고 TUI로 반드시 통과
        show = bool(
            event.is_status
            or event.is_error
            or is_progress
            or event.status in ("OK", "DONE", "FAIL", "WARN", "ABORT")
        )
        self._tick(event)
        raw_log.raw(
            "deps", event, to_tui=show,
            component_id=component_id, is_progress=is_progress,
        )

    @staticmethod
    def _had_action(tui_line):
        from chzzktube.core.log_event import safe_log_msg
        text = safe_log_msg(tui_line)
        verb = ("downloading", "fetching", "installing", "extracting",
                "reinstalling", "reconfiguring", "brew install")
        return any(v in text.lower() for v in verb)

    def _tick(self, tui_line):
        if self._had_action(tui_line):
            self.work_tick.emit()

    def _do_upgrade(self):
        import asyncio
        from chzzktube.infra.provisioning import ProvisioningManager

        mgr = ProvisioningManager(log_func=lambda evt, **kwargs: self._provision_cb(
            evt,
            is_status=kwargs.get("is_status", getattr(evt, "is_status", False)),
            is_error=kwargs.get("is_error", getattr(evt, "is_error", False)),
            component_id=kwargs.get("component_id", getattr(evt, "component_id", None)),
            is_progress=kwargs.get("is_progress", getattr(evt, "is_progress", False)),
        ))

        try:
            # [대역폭 수호] stale_only=True로 이미 정상인 의존성의 불필요한 재수급 차단
            results = asyncio.run(mgr.ensure_all(stale_only=True, channel=self.channel))
        except Exception as e:
            self.upgrade_done.emit(False, f"provisioning error: {e}")
            return

        ok = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if ok:
            raw_log.raw("deps", f"{', '.join(r.component for r in ok)} {'updated' if ok else 'installed'}")
        if failed:
            for r in failed:
                raw_log.raw("deps", emit_error_standard("DEPS", r.component.upper(), r.error or "unknown", "check logs (F12)"), to_tui=True)

        ok_overall = len(failed) == 0
        summary = f"{len(ok)} ok, {len(failed)} failed" if failed else f"{len(ok)} components provisioned"
        self.upgrade_done.emit(ok_overall, summary)