##### downloader.py - 다운로드 백그라운드 스레드
"""배치 다운로드 실행 워커 (DownloadWorker).

- 대상 평탄화·개별 분기(_td), 진행 틱(_pe), 배치 마감(_fin)을 worker 인자
  방식으로 호출하는 껝데기 오케스트레이션.
- [분리] YtLoggerBridge·AnalyzeWorker → analyze_worker.py / yt_logger_bridge.py.
  라우팅·종속 헬퍼는 각각의 전용 모듈에서만 import한다 (미사용 임포트 금지).
"""
import os
import yt_dlp

# [플러그인 기생 차단] analyze_worker.py와 동일 사유. 값 대입은 idempotent라
# 모듈 로딩 순서와 무관하게 안전 (첫 YoutubeDL 생성 전 1회 유효하면 된다).
yt_dlp.plugins.plugin_dirs.value = []

from PySide6.QtCore import QThread, Signal
from speed_window import SpeedWindow
from yt_logger_bridge import YtLoggerBridge
import progress_emitter as _pe
import target_downloader as _td
import finalizer as _fin

class DownloadWorker(QThread):
    log_concise = Signal(str, bool, bool)
    log_full = Signal(str)
    finished_all = Signal(int, int)

    def __init__(
        self,
        targets,
        cfg,
        state_dict,
        v_sel,
        a_sel,
        is_live_hint=False,
        v_spec=None,
        audio_desc="",
        yt_client="auto",
    ):
        super().__init__()
        self.targets = targets
        self.cfg = cfg
        self.state = state_dict
        self.v_sel = v_sel
        self.a_sel = a_sel
        self.audio_desc = str(audio_desc or "")
        self.v_spec = v_spec or {}
        self.is_live_hint = bool(is_live_hint)
        # [다운로드 일관성] 분석 단계에서 실증·통과한 클라이언트 (auto면 yt-dlp 기본)
        self.yt_client = str(yt_client or "auto")
        self.current_file = None
        self._meta_logged = False
        self._last_tick_t = 0.0
        self._speed_win = SpeedWindow()
        self._tick_file = None
        self._tick_last = 0
        self.live_partially_saved = False
        self.logger = YtLoggerBridge(self.log_full, self.log_concise)
        self.total_count = len(targets)
        self.current_idx = 1
        self.current_url = None

    def extract(self):
        """파이프라인 모듈에 넘길 DownloadContext를 생성한다 (D: 명시적 계약)."""
        from dl_context import DownloadContext

        return DownloadContext(
            cfg=self.cfg,
            v_sel=self.v_sel,
            a_sel=self.a_sel,
            v_spec=self.v_spec,
            audio_desc=self.audio_desc,
            logger=self.logger,
            log_concise=self.log_concise,
            current_url=self.current_url or "",
            current_file=self.current_file,
            state=self.state,
            speed_win=self._speed_win,
            total_count=self.total_count,
            current_idx=self.current_idx,
            is_live_hint=self.is_live_hint,
            live_partially_saved=self.live_partially_saved,
            yt_client=self.yt_client,
            targets=self.targets,
            finished_all=self.finished_all,
        )

    def _reset_loop_state(self):
        """매 타겟마다 필요한 상태 변수들을 한 번에 초기화."""
        self.current_file = None
        self._meta_logged = False
        self._last_tick_t = 0.0
        self._speed_win.reset()
        self._tick_file = None
        self._tick_last = 0

    def _emit_chzzk_header(self, ch_info, fmt):
        """yt-dlp에 chzzk 메타데이터를 전달하는 헤더 설정."""
        # chzzk API에서 받은 메타데이터를 yt-dlp에 전달하여 올바른 Downloader로 인식
        pass

    def run(self):
        """DownloadWorker 메인 스레드 — 하이퍼미니멀리즘 실행부."""
        ctx = self.extract()
        ctx.targets = _td.expand_targets(ctx)
        self.targets = ctx.targets  # 동기화 (current_file 등 내부 상태 유지)
        self.total_count = len(self.targets)
        failed_targets = []
        success_count = 0

        try:
            for idx, url in enumerate(self.targets, 1):
                self.current_idx = idx
                self.current_url = url
                ctx.current_idx = idx
                ctx.current_url = url
                if self.state["canceled"]:
                    break
                if self.state["skip"]:
                    self.state["skip"] = False
                    self._reset_loop_state()
                    ctx._meta_logged = False
                    self.log_concise.emit(
                        _pe.emit_dl("SKIP", "-", spec="-", speed="-", pct=None, bar_frac=None,
                                    msg=f"skipped ({idx}/{self.total_count})"),
                        False, False,
                    )
                    continue
                self._reset_loop_state()
                ctx._meta_logged = False
                ctx.current_file = None

                if _td.download_target(ctx, url, failed_targets):
                    success_count += 1

            _fin.finalize(ctx, self.total_count, failed_targets, success_count)

        except Exception as ex:
            if "CANCELED_BY_USER" in str(ex) or "중지되었습니다" in str(ex) or self.state["canceled"]:
                pass
            else:
                self.log_concise.emit(
                    _pe.emit_err(str(ex)), False, True
                )

            _fin.finalize(ctx, self.total_count, failed_targets, success_count)

