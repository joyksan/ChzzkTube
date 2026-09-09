### update_worker.py - DEPS 체크/자동 업그레이드 워커
"""시작 시퀀스의 의존성 확인·수급을 담당하는 백그라운드 워커 (UpdateWorker).

- _do_check : updater.check_deps() 결과를 line 시그널로(DEPS 5줄), CLI 원문을
  full 시그널로(F12) 분리 전송. stale 패키지는 check_done(list)으로 반환.
- _do_upgrade: PyPI(yt-dlp/streamlink) + ffmpeg + node 순차 수급.
  각 수급의 실제 진행 여부를 _had_action 판별해 '요약 결론' 1줄만 남긴다.
- [분리] dialogs.py에서 추출 — 대화상자 컬렉션과 워커의 수명·계층이 다르다.
- [시그널 계약] check_done(list) → main._on_update_check_done,
  upgrade_done(bool,str) → StartupCoordinator.report_upgrade.
"""
import os
import traceback

import updater
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
    # line = (msg, is_status, is_error) — POTProviderWorker와 동일 시그널 계약.
    # 진행률/상태 로그는 is_status=True로 emit해야 ConciseLogConsole이 같은 줄을
    # 덮어쓴다(갱신형). raw 상세(pip/다운로드 출력)는 full → F12(상세 로그)로만 흘러간다.
    line = Signal(str, bool, bool)
    full = Signal(str, bool)  # (raw 원문, is_status) — True면 F12에서 마지막 줄 갱신(진행률 덮어쓰기)

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
            self.full.emit(f"UpdateWorker crash: {traceback.format_exc()}", False)
            self.line.emit(emit_component("SYS", "FAIL", "deps", f"worker crash: {e}"), False, True)
            self.check_done.emit([])

    def _do_check(self):
        """버전 확인 — 메인 콘솔(deps 상태 5줄) + F12(CLI 원문).

        [min profile] 메인 콘솔에는 상태 라인 5개 — fzf/lazygit 톤은 공백이 곧 정보.
        F12에는 실제 CLI를 실행해 셸에서 칠 때 보이는 원문 출력 그대로를
        적재한다. TUI 상태와 CLI 원문을 겹쳐 띄우지 않는다(교체 원칙).
        """
        stale = []
        # [단일 호출] check_deps 내부 pot_readiness에 log_func 직접 전달 —
        # 판정+로그 1회 (별도 호출 시 standby 2중 출력).
        import raw_log
        for label, status, ver in updater.check_deps(
            log_func=lambda m: raw_log.raw("pot-readiness", m)
        ):
            self.line.emit(emit_component("DEPS", status, label, ver), False, False)
        # [raw] 실제 CLI 실행 — 터미널에서 직접 친 것과 동일한 원문을 F12에 기록.
        # ffmpeg -version 원문은 configuration: 1줄이 500자 — 6줄+160자 절단.
        for label, args in _RAW_VERSION_CMDS:
            cmdline, out = updater.cli_raw(label, *args, max_lines=6, max_width=160)
            if cmdline and out:
                self.full.emit(f"$ {cmdline}", False)
                for line in out.splitlines():
                    self.full.emit(line, False)
        # 수동 체크용 stale 생성 (outdated_packages) — 사용자 채널 반영.
        # auto_update_check off 면 PyPI 폴링 스킵 (stale 미생성 → upgrade 워커는 수급만)
        if self.check_updates:
            for label, pypi_name, cur, latest in updater.outdated_packages(channel=self.channel):
                stale.append((label, pypi_name, cur, latest))
                self.full.emit(f"[stale] {label} {cur} → {latest}", False)
        else:
            self.full.emit("pypi update check: disabled (auto_update_check=off)", False)
        self.check_done.emit(stale)

    def _provision_cb(self, tui_line, is_status=False, is_error=False):
        """설치/수급 진행 로그 — 메인은 TUI(갱신형), F12는 raw 원문.

        [2분기 원칙] F12에는 TUI 규격을 그대로 베끼지 않는다. 지금 줄의
        마지막 메시지부만 떼어 원문으로 적재 — is_status=True면 F12에서도
        마지막 줄을 덮어써서 설치 진행률이 한 줄로 갱신된다(사용자 요구).
        """
        raw = tui_line.rsplit("│", 1)[-1].strip() if "│" in tui_line else tui_line.strip()
        if raw:
            self.full.emit(raw, bool(is_status))
        status = tui_line.split("│")[1].strip() if "│" in tui_line else ""
        if is_error or status in ("FAIL", "WARN", "ABORT"):
            self.line.emit(tui_line, is_status, is_error)
        elif is_status:
            self.line.emit(tui_line, True, False)

    @staticmethod
    def _had_action(tui_line):
        """실제 수급 작업(다운로드/설치/추출 등)이 있었는지 — RUN 진행 동사 판별."""
        verb = ("downloading", "fetching", "installing", "extracting",
                "reinstalling", "reconfiguring", "brew install")
        return any(v in tui_line.lower() for v in verb)

    def _do_upgrade(self, stale_updates=None):
        from log_console import emit_component
        import components
        import pot_provider
        ok_overall = True
        summaries = []

        # 1. PyPI packages (yt-dlp, streamlink) — stale로 확인된 것만
        stale_updates = stale_updates or []
        if stale_updates:
            for _label, name, cur, latest in stale_updates:
                self.full.emit(f"[stale] {name}: {cur} → {latest}", False)
            pypi_names = [p[1] for p in stale_updates]
            code, tail = updater.upgrade_packages(pypi_names, channel=self.channel)
            for l in tail.splitlines():
                if l.strip():
                    # raw 출력(pip/다운로드)은 상세 로그(F12)로만 — TUI 콘솔 오염 방지
                    self.full.emit(l.strip(), False)
            if code != 0:
                ok_overall = False
                summaries.append(f"pypi ({', '.join(pypi_names)}) failed")
            else:
                summaries.append(f"{', '.join(pypi_names)} updated")
        else:
            self.full.emit("pypi: all up-to-date", False)

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
            self.line.emit(emit_component("DEPS", "FAIL", "ffmpeg", ff_err), False, True)
        elif ffmpeg_acted[0]:
            summaries.append("ffmpeg provisioned")
        else:
            self.full.emit("ffmpeg: ok (no action needed)", False)

        # 3. node auto-provisioning (POT server runtime)
        node_acted = [False]
        def _node_cb(msg, is_status=True, is_error=False):
            if self._had_action(msg):
                node_acted[0] = True
            # pot_provider log_func 계약 (msg, is_status, is_error)
            self._provision_cb(emit_component("DEPS", "RUN", "node", msg), is_status, is_error)

        try:
            node_ok = pot_provider.ensure_node_runtime(_node_cb)
            if node_ok:
                if node_acted[0]:
                    summaries.append("node provisioned")
                else:
                    self.full.emit("node: ok (no action needed)", False)
            else:
                ok_overall = False
                summaries.append("node setup failed")
                self.line.emit(emit_component("DEPS", "FAIL", "node", "setup failed"), False, True)
        except Exception as e:
            ok_overall = False
            summaries.append(f"node: {e}")
            self.line.emit(emit_component("DEPS", "FAIL", "node", str(e)), False, True)

        summary = "; ".join(summaries) if summaries else ""
        self.upgrade_done.emit(ok_overall, summary)