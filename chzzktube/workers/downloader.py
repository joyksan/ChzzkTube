##### downloader.py - 다운로드 백그라운드 스레드
"""배치 다운로드 실행 워커 (DownloadWorker).

- 대상 평탄화·개별 분기(_td), 진행 틱(_pe), 배치 마감(_fin)을 worker 인자
  방식으로 호출하는 껍데기 오케스트레이션.
- [분리] YtLoggerBridge·AnalyzeWorker → analyze_worker.py / yt_logger_bridge.py.
  라우팅·종속 헬퍼는 각각의 전용 모듈에서만 import한다 (미사용 임포트 금지).
"""
import yt_dlp
from PySide6.QtCore import QThread, Signal

import chzzktube.core.raw_log as raw_log
from chzzktube.core.dl_platform import _dl_platform
from chzzktube.core.speed_window import SpeedWindow
from chzzktube.core.yt_logger_bridge import YtLoggerBridge
import chzzktube.pipeline.finalizer as _fin
import chzzktube.pipeline.progress_emitter as _pe
import chzzktube.pipeline.target_downloader as _td

# [플러그인 기생 차단] analyze_worker.py와 동일 사유. 값 대입은 idempotent라
# 모듈 로딩 순서와 무관하게 안전 (첫 YoutubeDL 생성 전 1회 유효하면 된다).
# 모든 최상단 import가 끝난 직후, 클래스 정의 전에 배치하여 E402를 원천 차단한다.
yt_dlp.plugins.plugin_dirs.value = []

class DownloadWorker(QThread):
    # [v3.3.0] 로그는 raw 버스(raw_log.raw) 단일 경유 — log_concise/log_full 시그널 폐기.
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
        self.logger = YtLoggerBridge()  # [v3.3.0] 버스 직행 — 시그널 인자 폐기
        self.total_count = len(targets)
        self.current_idx = 1
        self.current_url = None
        self._live_proc = None  # 라이브 녹화 프로세스 핸들 (앱 종료 시 정리용)
        self._ctx = None  # [A4] DownloadContext 참조 — 라이브 proc는 ctx에 부착된다

    def extract(self):
        """파이프라인 모듈에 넘길 DownloadContext를 생성한다 (D: 명시적 계약)."""
        from chzzktube.pipeline.dl_context import DownloadContext

        return DownloadContext(
            cfg=self.cfg,
            v_sel=self.v_sel,
            a_sel=self.a_sel,
            v_spec=self.v_spec,
            audio_desc=self.audio_desc,
            logger=self.logger,
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
        """매 타겟마다 필요한 상태 변수들을 한 번에 초기화 (worker 내부용)."""
        self._last_tick_t = 0.0
        self._tick_file = None
        self._tick_last = 0

    def run(self):
        """DownloadWorker 메인 스레드 — 하이퍼미니멀리즘 실행부."""
        ctx = self.extract()
        self._ctx = ctx  # [A4] 라이브 녹화 proc 핸들이 ctx._live_proc에 부착된다
        ctx.targets = _td.expand_targets(ctx)
        self.targets = ctx.targets  # 동기화 (current_file 등 내부 상태 유지)
        self.total_count = len(self.targets)
        failed_targets = []
        success_count = 0

        try:
            for idx, url in enumerate(self.targets, 1):
                ctx.advance_target(idx, url)
                self.current_idx = ctx.current_idx
                self.current_url = ctx.current_url

                if self.state["canceled"]:
                    break
                if self.state["skip"]:
                    self.state["skip"] = False
                    raw_log.raw(
                        "dl",
                        _pe.emit_dl("SKIP", scope=_dl_platform(url), msg=f"skipped ({idx}/{self.total_count})"),
                        to_tui=True,
                    )
                    continue

                if _td.download_target(ctx, url, failed_targets):
                    success_count += 1

            _fin.finalize(ctx, self.total_count, failed_targets, success_count)

        except Exception as ex:  # noqa: BLE001
            # 워커 최상위 안전망이므로 BLE001 무시 명시
            if "CANCELED_BY_USER" in str(ex) or "중지되었습니다" in str(ex) or self.state["canceled"]:
                pass
            else:
                raw_log.raw("dl", _pe.emit_err(str(ex)), to_tui=True)

            _fin.finalize(ctx, self.total_count, failed_targets, success_count)

    def kill_live_process(self):
        """[A4] 라이브 녹화 프로세스 정리 — worker·ctx 양쪽 핸들을 모두 킬."""
        handles = (self._live_proc, getattr(getattr(self, "_ctx", None), "_live_proc", None))
        for proc in handles:
            if proc is None:
                continue
            try:
                proc.kill()
                raw_log.raw(
                    "dl",
                    _pe.emit_event(
                        "DL",
                        "WARN",
                        "FFMP",
                        "killed live recorder on worker terminate",
                        is_error=True,
                    ),
                    to_tui=True,
                )
            except OSError:
                # 프로세스가 이미 종료되었거나 권한 부족일 때만 안전하게 무시
                pass
        self._live_proc = None

    def terminate(self):
        """스레드 강제 종료 시 라이브 녹화 프로세스도 함께 정리."""
        self.kill_live_process()
        super().terminate()

