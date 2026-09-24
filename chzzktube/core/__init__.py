##### core/__init__.py - 공통 상수 및 유틸리티
"""chzzktube.core 패키지 공통 상수 및 유틸리티."""

# ─── 네트워크 타임아웃 상수 (초) ────────────────────────────────────────────
# 일관된 타임아웃 정책: 연결 10초, 읽기 30초, 대용량 다운로드 60초
CONNECT_TIMEOUT = 10.0      # TCP 연결 수립 대기
READ_TIMEOUT = 30.0         # HTTP 응답 헤더/바디 읽기 대기
DOWNLOAD_TIMEOUT = 60.0     # 대용량 파일 다운로드 (streaming read)

# ghcr.io 토큰 등 짧은 API 호출
SHORT_API_TIMEOUT = 15.0

# POT 서버 핑 등 매우 짧은 호출
PING_TIMEOUT = 1.5

# FFmpeg 버전 확인 등 로컬 프로세스
LOCAL_PROC_TIMEOUT = 10.0

# ─── 파일 권한 상수 ──────────────────────────────────────────────────────
# 임시 파일은 소유자만 읽기/쓰기 (0o600)
TEMP_FILE_MODE = 0o600
# 실행 파일은 소유자 실행 + 그룹/타자 읽기/실행 (0o755)
EXECUTABLE_FILE_MODE = 0o755
