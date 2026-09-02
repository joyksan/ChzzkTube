### controller.py - 다운로드 세션의 상태 머신 및 DownloadWorker 생명주기 관리
import os
import re

from downloader import DownloadWorker

class DownloadController:
    """다운로드 세션의 상태(state)와 워커 생명주기를 담당하는 컨트롤러.

    계약:
    *  state 딕셔너리는 DownloadWorker에 참조 그대로 전달된다. 즉, 워커 스레드와 UI 스레드가 동일 객체를 공유하며 기존 MainWindow.dl_state와 완전히 동치이다.
    *  스레드 경계 — state 플래그는 단방향 쓰기: canceled/skip/force_discard 는
       UI 스레드(request_cancel/request_skip/begin/end)만 쓰고 워커 스레드는
       읽기만 한다. CPython GIL 하에서 dict 단일 키 읽기/쓰기는 원자적이고
       각 키의 쓰기 주체가 하나뿐이므로 lock 없이도 경쟁상태(lost update)가
       발생하지 않는다.
    *  워커 → UI 통보는 절대 state가 아니라 Qt 시그널(log_concise/log_full/
       finished_all)로만 — 시그널 emit은 스레드 안전(QueuedConnection으로
       수신 스레드 큐에 적재)이므로 UI 위젯은 워커에서 직접 조작 금지.
    *  UI 조작(버튼/로그/진행바)은 view(MainWindow)의 메서드를 통해서만 수행한다. """

    def __init__(self, view):
        self.view = view
        self.state = {
            "running": False,
            "canceled": False,
            "skip": False,
            "force_discard": False,
        }
        self.worker = None

    @property
    def running(self):
        return self.state["running"]

    ### ── 순수 로직: 타겟 파싱 ──────────────────────────────────
    @staticmethod
    def parse_targets(raw_text, dedup=False):
        """URL/TXT 입력을 다운로드 타겟 목록으로 파싱.
        *  TXT 파일 경로면 줄 단위로 읽는다 (# 주석 제외). 실패 시 ValueError.
        *  www. 로 시작하는 항목은 https:// 접두사를 보정한다.
        *  watch?v= 단일 영상 주소 뒤 &list= / &index= / &start_radio= 플레이리스트 파라미터를 강제 제거한다.
        *  dedup=True 이면 중복 타겟을 제거한다. """
        targets = []
        if os.path.isfile(raw_text) and raw_text.lower().endswith(".txt"):
            try:
                with open(raw_text, "r", encoding="utf-8") as f:
                    for l in f:
                        t = l.strip()
                        if t and not t.startswith("#"):
                            targets.append(
                                "https://" + t if t.startswith("www.") else t
                            )
            except Exception as e:
                raise ValueError(f"TXT 읽기 실패: {e}") from e
        else:
            for l in raw_text.splitlines():
                t = l.strip()
                if t:
                    targets.append("https://" + t if t.startswith("www.") else t)

        # [핵심] watch?v= 단일 영상 뒤에 붙은 플레이리스트 파라미터 강제 제거!
        cleaned_targets = []
        for u in targets:
            if "watch?v=" in u and "&list=" in u:
                u = re.sub(r"&list=[^&]+", "", u)
                u = re.sub(r"&index=[^&]+", "", u)
                u = re.sub(r"&start_radio=[^&]+", "", u)
            cleaned_targets.append(u)
        targets = cleaned_targets

        if dedup:
            targets = list(dict.fromkeys(targets))
        return targets

    ### ── 세션 상태 머신 ────────────────────────────────────────
    def begin(self):
        self.state.update(
            {"running": True, "canceled": False, "skip": False, "force_discard": False}
        )

    def end(self):
        self.state.update(
            {"running": False, "canceled": False, "skip": False, "force_discard": False}
        )

    def request_cancel(self):
        if self.running:
            self.state["canceled"] = True

    def request_skip(self):
        if self.running:
            self.state["skip"] = True

    ### ── 워커 생명주기 ─────────────────────────────────────────
    def spawn_worker(
        self,
        targets,
        cfg,
        video_id,
        audio_id,
        is_live_hint=False,
        v_spec=None,
        audio_desc="",
    ):
        """DownloadWorker 생성 + 시그널 연결 + 구동."""
        v = self.view
        w = DownloadWorker(
            targets,
            cfg,
            self.state,
            video_id,
            audio_id,
            is_live_hint=is_live_hint,
            v_spec=v_spec,
            audio_desc=audio_desc,
        )
        w.log_concise.connect(v.append_concise_log)
        w.log_full.connect(v.append_full_log)
        w.finished_all.connect(v.on_download_finished)
        self.worker = w
        w.start()

    def shutdown(self, wait_ms=1000):
        """앱 종료 시 스레드 안전 중단 (closeEvent용)."""
        if self.worker and self.worker.isRunning():
            self.state["canceled"] = True
            self.worker.wait(wait_ms)
