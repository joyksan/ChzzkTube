# Implementation Plan: v3.9.0 대규모 리팩토링 (기술부채 해소 + 방향성 재정립)

## Overview
v3.8.5 → v3.9.0 minor. 대형 리팩토링 + 아키텍처 재편. 기존 코드에 매몰되지 않고
개발 방향성(yt-dlp 순정 위임 3계층, raw 버스 단일 진입, 격리 수급)과
기능 구현 및 성능 향상을 목표로 한다. F12 방침은 선택지 B 확정:
화면 교체 + 원문 보존 분리 (HANDOVER §5-33 직교 분리 준수).

F12 계약 (B):
- 영구 스토리지(history 파일 + raw full_events ring 4096)는 전량 무삭제 순차 기록.
- GUI 뷰(VerboseLogWindow)와 메모리 링 버퍼(_full_log_buf)는 진행 틱
  (is_status=True 또는 component_id 보유)을 개행 적재 금지 → 제자리 치환.
- 창 열림: win.append(..., component_id) 실시간 치환.
- 창 닫힘: _full_log_buf 상태 줄 스냅샷 치환.

## Architecture Decisions
- raw_log.raw() 단일 진입 유지. 호출점 흩뿌리기 금지 (§6).
- yt-dlp 순정 위임 유지. 수동 client_chain 부활 금지 (§5-6.x).
- evermeet/SHA 미제공 소스 폴백 신설 금지 (§6).
- node lib/ 유기 금지. ffmpeg 평탄화와 node 보존 구분 (§5-29).
- stale_only=True 강제, 마감 이벤트 TUI 관통 보장 (§5-30).
- format_log_line rstrip 원칙 유지 (§5-31).
- Thin Wrapper 신설 금지. 모듈 함수 직접 호출.
- mirrors/*.md 손편집 금지. .py 원본 + sync_mirrors.py 재생성.

## Task List (→ tasks/refactor_v3.9.0_todo.md)
Phase 0 기준선 / Phase 1 P0 정합성 / Phase 2 todo 잔재 통합 /
Phase 3 F12 B 확정 반영 / Phase 4 구조 분해 / Phase 5 성능·보안 /
Phase 6 검증·버전업. 상세는 todo 파일.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| F12 계약 변경 회귀 | High | 코드+테스트 동시 변경, CHANGELOG 기록 |
| macOS 실네트워크 부재 | Med | mock 계약 테스트를 유일 기준 |
| MainWindow 분해 회귀 | High | 슬라이스마다 focused→전체 테스트 |
| 전면 재수정 충동 | High | /build 얇은 슬라이스 + /tdd RED-GREEN-REFACTOR 강제 |

## Open Questions (해결됨)
- F12 방침: B 확정 (사용자 결정).
- 파일명: refactor_v3.9.0_* 로 버전 병기 (사용자 결정).
- 나머지: HANDOVER 정독으로 해결.
