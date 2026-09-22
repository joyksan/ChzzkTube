# Implementation Plan: TUI/F12 로그 보존 및 macOS FFmpeg Bottle 경로 안정화

## Overview
동일 컴포넌트의 진행 라인은 TUI/F12에서 갱신하되, F12 버퍼와 파일 로그에는 모든 원문 틱을 누적한다. macOS Homebrew Bottle 내부의 중첩 `bin/ffmpeg`는 앱 격리 캐시의 `ffmpeg/bin/ffmpeg`로 정규화해 설치·검증한다.

## Architecture Decisions
- TUI는 `component_id`와 `is_progress`로 동일 라인만 갱신하고, 완료 이벤트는 해당 라인을 확정한다.
- F12는 `component_id`로 화면 라인을 갱신하지만 `_full_log_buf`에는 모든 틱을 별도 원문으로 보존한다.
- macOS Bottle은 중첩 실행 파일을 재귀 탐색해 `writable_base()/ffmpeg/bin/ffmpeg`로 복사하고, `ffprobe`도 함께 보존한다.
- 기존 정적 FFmpeg 폴백과 URL 출처 계약은 유지하며, 실패 원인은 실제 후보 경로와 오류를 포함한다.

## Task List

### Task 1: 로그 데이터 계약 및 F12 초기화 정리
- [ ] `VerboseLogWindow.__init__` 중복 제거
- [ ] `_mirror_event_full`과 `_mirror_full_log`가 `component_id`를 보존
- [ ] `_full_log_buf`가 진행 틱을 모두 누적하고 원문을 보존
- [ ] F12 화면 갱신과 원문 누적 계약을 분리
- [ ] 관련 회귀 테스트 추가

### Task 2: TUI 동일 라인 갱신 및 완료 잠금
- [ ] `ConciseLogConsole`이 `component_id` 기반 진행 라인을 갱신
- [ ] `_render_concise`가 `is_progress`를 보존하고 완료 시 확정
- [ ] 기존 progress 회귀 테스트 통과

### Task 3: macOS FFmpeg Bottle 경로 정규화
- [ ] Bottle 내부 중첩 `bin/ffmpeg` 탐색 및 캐시 루트 경로 복사
- [ ] `ffprobe` 동시 보존
- [ ] `ffmpeg_exe()`가 정규화된 경로를 반환
- [ ] 검증 실패 시 정적 폴백 유지 및 상세 오류 제공
- [ ] macOS 경로 회귀 테스트 추가

### Task 4: 외부 수급·미디어 URL 감사
- [ ] FFmpeg, Node.js, bgutil, yt-dlp/streamlink 출처 추적
- [ ] Chzzk/Naver/YouTube/CDN 미디어 URL 사용 경로 추적
- [ ] 실제 다운로드·실행 경로와 정적 URL 계약 테스트 추가

### Task 5: 검증
- [ ] focused pytest 통과
- [ ] 전체 pytest 통과
- [ ] Python compile check 통과
- [ ] diff와 변경 파일 검토

## Risks and Mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| Qt 위젯 초기화 중복 | F12 위젯 상태 누락 | 중복 `__init__` 제거 및 인스턴스 테스트 |
| macOS Bottle 구조 변화 | FFmpeg 검증 실패 | 재귀 탐색, 정규화, 정적 폴백 |
| 네트워크 미연결 | 실시간 수급 검증 불가 | URL/경로 정적 회귀 테스트와 실패 경로 검증 |

## Open Questions
- 실제 네트워크 연결 가능 여부는 런타임 환경에서 확인 필요.
