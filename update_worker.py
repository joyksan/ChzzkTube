### update_worker.py - DEPS 체크/자동 업그레이드 워커
"""시작 시퀀스의 의존성 확인·수급을 담당하는 백그라운드 워커 (UpdateWorker).

- _do_check : updater.check_deps() 결과를 DEPS 이벤트로(TUI 5줄), CLI 원문을
  raw 문자열로(F12) 버스 단일 경유 전송. stale 패키지는 check_done(list)으로 반환.
- _do_upgrade: PyPI(yt-dlp/streamlink) + ffmpeg + node 순차 수급.
  각 수급의 실제 진행 여부를 _had_action 판별해 '요약 결론' 1줄만 남긴다.
- [분리] dialogs.py에서 추출 — 대화상자 컬렉션과 워커의 수명·계층이 다르다.
- [시그널 계약] check_done(list) → main._on_update_check_done,
  upgrade_done(bool,str) → StartupCoordinator.report_upgrade.
- [v3.3.0] 로그는 raw 버스(raw_log.raw) 단일 경유 — line/full 시그널 폐기.
"""
import os
import traceback

import updater
import raw_log
from log_event import LogEvent
from PySide6.QtCore import QThread, Signal
from log_console import emit_component

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

    def __init__(self, parent=None, upgrade=False, stale_updates=None, channel='stable', check_updates=True):
        super().__init__(parent)
        self.upgrade = upgrade
        self.stale_updates = stale_updates or []
        self.channel = channel
        self.check_updates = check_updates

    def run(self):
        try:
            if self.upgrade:
                self._do_upgrade(self.stale_updates)
            else:
                self._do_check()
        except Exception as e:
            import traceback
            traceback.print_exc()
            raw_log.raw("deps", LogEvent(stage="SYS", status="FAIL", platform="deps",
                                         msg=f"worker crash: {e}", is_error=True), to_tui=True)
            self.check_done.emit([])

    def _do_check(self):
        """버전 확인 — 메인 콘솔(deps 상태 5줄) + F12(CLI 원문). 버스 단일 경유.

        [min profile] 메인 콘솔에는 상태 라인 5개 — fzf/lazygit 톤은 공백이 곧 정보.
        F12에는 실제 CLI를 실행해 셸에서 칠 때 보이는 원문 출력 그대로를
        적재한다. TUI 상태와 CLI 원문을 겹쳐 띄우지 않는다(교체 원칙).
        """
        stale = []
        # [단일 호출] check_deps 내부 pot_readiness에 log_func 직접 전달 —
        # 판정+로그 1회 (별도 호출 시 standby 2중 출력).
        for label, status, ver in updater.check_deps(
            log_func=lambda m: raw_log.raw(
                "pot-readiness",
                LogEvent(stage="POT", status="RUN", platform="pot", spec="-", msg=str(m)),
            )
        ):
            raw_log.raw("deps", emit_component("DEPS", status, label, ver), to_tui=True)
        # [raw] 실제 CLI 실행 — 수집은 원문 전량(history), F12 적재 시 절취(뷰).
        # ffmpeg -version 원문은 configuration: 1줄이 500자 — 적재 시 6줄+160자 절단.
        for label, args in _RAW_VERSION_CMDS:
            cmdline, out = updater.cli_raw(label, *args)
            if cmdline and out:
                raw_log.raw("deps-cli", f"$ {cmdline}")
                for line in updater.truncate_for_full_log(out).splitlines():
                    raw_log.raw("deps-cli", line)
        # 수동 체크용 stale 생성 (outdated_packages) — 사용자 채널 반영.
        # auto_update_check off 면 PyPI 폴링 스킵 (stale 미생성 → upgrade 워커는 수급만)
        if self.check_updates:
            for label, pypi_name, cur, latest in updater.outdated_packages(channel=self.channel):
                stale.append((label, pypi_name, cur, latest))
                raw_log.raw("pypi", f"[stale] {label} {cur} → {latest}")
        else:
            raw_log.raw("pypi", "pypi update check: disabled (auto_update_check=off)")
        self.check_done.emit(stale)

    def _provision_cb(self, msg, is_status=False, is_error=False):
        """설치/수급 진행 로그 — F12는 항상 원문, TUI는 상태/진행만 (버스 단일 경유).

        components/node_provider의 콜백은 LogEvent(emit_component 빌더) 또는
        문자열을 넘긴다 — 둘 다 LogEvent로 정규화해 버스로 보낸다.
        is_status=True면 TUI에서도 마지막 줄을 덮어써 설치 진행률이 한 줄로 갱신된다.
        """
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
                platform="deps", msg=str(msg),
                is_status=is_status, is_error=is_error,
            )
        show = bool(event.is_status or event.is_error
                    or event.status in ("FAIL", "WARN", "ABORT"))
        raw_log.raw("deps", event, to_tui=show)

    @staticmethod
    def _had_action(tui_line):
        """실제 수급 작업(다운로드/설치/추출 등)이 있었는지 — RUN 진행 동사 판별."""
        from log_event import LogEvent
        text = tui_line.msg if isinstance(tui_line, LogEvent) else str(tui_line)
        verb = ("downloading", "fetching", "installing", "extracting",
                "reinstalling", "reconfiguring", "brew install")
        return any(v in text.lower() for v in verb)

    def _do_upgrade(self, stale_updates=None):
        import components
        import pot_provider
        ok_overall = True
        summaries = []

        # 1. PyPI packages (yt-dlp, streamlink) — stale로 확인된 것만
        stale_updates = stale_updates or []
        if stale_updates:
            for _label, name, cur, latest in stale_updates:
                raw_log.raw("pypi", f"[stale] {name}: {cur} → {latest}")
            pypi_names = [p[1] for p in stale_updates]
            code, tail = updater.upgrade_packages(pypi_names, channel=self.channel)
            for l in tail.splitlines():
                if l.strip():
                    # raw 출력(pip/다운로드)은 F12 원문으로 — TUI 콘솔 오염 방지
                    raw_log.raw("pip", l.strip())
            if code != 0:
                ok_overall = False
                summaries.append(f"pypi ({', '.join(pypi_names)}) failed")
            else:
                summaries.append(f"{', '.join(pypi_names)} updated")
        else:
            raw_log.raw("pypi", "pypi: all up-to-date")

        # 2. ffmpeg auto-provisioning — 실제 수급이 없으면 간결 무표기
        ffmpeg_acted = [False]
        def _ffmpeg_cb(msg, is_status=False, is_error=False, *a):
            if self._had_action(msg):
                ffmpeg_acted[0] = True
            self._provision_cb(msg, is_status, is_error)

        ff_err = components.ensure_ffmpeg(_ffmpeg_cb)
        if ff_err:
            ok_overall = False
            summaries.append(f"ffmpeg: {ff_err}")
            raw_log.raw("deps", emit_component("DEPS", "FAIL", "ffmpeg", ff_err, is_error=True),
                        to_tui=True)
        elif ffmpeg_acted[0]:
            summaries.append("ffmpeg provisioned")
        else:
            raw_log.raw("ffmpeg", "ffmpeg: ok (no action needed)")

        # 3. node auto-provisioning (POT server runtime)
        node_acted = [False]
        def _node_cb(msg, is_status=True, is_error=False):
            if self._had_action(msg):
                node_acted[0] = True
            # [버스 단일 경유] TUI 틱(갱신형) + F12 원문 — emit_component 재포장 폐기
            if isinstance(msg, LogEvent):
                raw_log.raw("deps", msg, to_tui=True)
            else:
                raw_log.raw(
                    "deps",
                    LogEvent(stage="DEPS", status="RUN", platform="node", msg=str(msg),
                             is_status=is_status, is_error=is_error),
                    to_tui=True,
                )

        try:
            node_ok = pot_provider.ensure_node_runtime(_node_cb)
            if node_ok:
                if node_acted[0]:
                    summaries.append("node provisioned")
                else:
                    raw_log.raw("node", "node: ok (no action needed)")
            else:
                ok_overall = False
                summaries.append("node setup failed")
                raw_log.raw("deps", emit_component("DEPS", "FAIL", "node", "setup failed", is_error=True),
                            to_tui=True)
        except Exception as e:
            ok_overall = False
            summaries.append(f"node: {e}")
            raw_log.raw("deps", emit_component("DEPS", "FAIL", "node", str(e), is_error=True),
                        to_tui=True)

        summary = "; ".join(summaries) if summaries else ""
        self.upgrade_done.emit(ok_overall, summary)