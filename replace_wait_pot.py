import sys
with open('c:/dev/ChzzkTube/main.py','r',encoding='utf-8') as f:
    c = f.read()

old = '''    def _wait_pot_if_needed(self):
        \"\"\"PO Token 필요 영상(연령제한 등)인 경우 POT 서버 기동 트리거.
        논블로킹 — 큐 메커니즘(_pending_download + _on_pot_finished)이 완료 후 실행.\"\"\"
        info = (self.extracted_data or {}).get("info") or {}
        age_limit = info.get("age_limit") or 0
        availability = info.get("availability") or ""
        needs_pot = age_limit > 0 or (
            isinstance(availability, str) and availability.lower() in (
                "needs_auth", "premium_only", "subscriber_only", "private"
            )
        )
        if not needs_pot:
            return

        # POT 서버가 이미 실행 중이면 바로 진행
        from po_client import server_ping
        if server_ping():
            return

        # POT 서버가 없으면 기동만 트리거 (대기는 큐가 처리)
        self.append_concise_log(
            log_console.emit_event("POT", "RUN", "pot", "starting server..."),
            is_status=True,
            is_error=False,
        )
        self._start_pot_provider()
        # 여기서 리턴 — _on_pot_finished에서 _pending_download 실행'''

new = '''    def _wait_pot_if_needed(self):
        \"\"\"PO Token 필요 영상(연령제한 등)인 경우 POT 서버 기동 트리거.
        논블로킹 — 큐 메커니즘(_pending_download + _on_pot_finished)이 완료 후 실행.\"\"\"
        info = (self.extracted_data or {}).get("info") or {}
        age_limit = info.get("age_limit") or 0
        availability = info.get("availability") or ""
        needs_pot = age_limit > 0 or (
            isinstance(availability, str) and availability.lower() in (
                "needs_auth", "premium_only", "subscriber_only", "private"
            )
        )
        if not needs_pot:
            return

        # POT 서버가 이미 실행 중이면 바로 진행
        from po_client import server_ping
        if server_ping():
            return

        # POT 서버가 없으면 기동만 트리거 (대기는 큐가 처리)
        self.append_concise_log(
            log_console.emit_event("POT", "RUN", "pot", "starting server..."),
            is_status=True,
            is_error=False,
        )
        # [POTManager] gate 모드로 서버 기동 (중복 스폰 가드 내장)
        self._pot_manager.ensure_ready("gate")'''

c = c.replace(old, new)
with open('c:/dev/ChzzkTube/main.py','w',encoding='utf-8') as f:
    f.write(c)
print('done')