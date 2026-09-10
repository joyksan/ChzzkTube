import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('c:/dev/ChzzkTube/startup_coordinator.py', 'r', encoding='utf-8') as f:
    content = f.read()

i = content.find('def _try_emit_ready')
j = content.find('\n\n    def ', i + 1)

new_method = '''def _try_emit_ready(self):
        \"\"\"
        모든 필수 단계가 완료되면 READY 로그 출력.
        순서: DEPS → (upgrade 시 upgrade 완료) → POT (필요 시) → READY
        \"\"\"
        with self._lock:
            if self._state.can_emit_ready():
                self._state.mark_ready_emitted()
                self._emit_log("SYS", "READY", "SYS", "-", "ready", is_status=False, is_error=False)

                # 작업 로그와 구분하기 위한 separator
                self._view.add_concise_task_separator()

                # [순서 고정] 플래그를 먼저 세워야 update_ui_state()가
                # url_input.setEnabled(True)로 판단한다 (역순이면 영구 lock).
                self._view._startup_completed = True

                # UI 상태 업데이트 (입력 잠금 해제 등)
                self._view.update_ui_state()
'''

content = content[:i] + new_method + content[j:]

with open('c:/dev/ChzzkTube/startup_coordinator.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('done')