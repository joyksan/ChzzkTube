# log_bus.py — [폐기됨 v3.3.0]
#
# raw_log로 통합됐다. 버스 불변식: "앱의 모든 행동은 raw_log.raw() 하나로
# 수신된다" — 이중 버스는 경로 2개를 의미하므로 유지하지 않는다.
#
# [마이그레이션]
# - emit(msg, channel=FULL)  → raw_log.raw(tag, msg)            (F12+history 전량)
# - emit(msg, channel=BOTH)  → raw_log.raw(tag, LogEvent(...), to_tui=True)
#
# [삭제 예정] 사용처(startup_coordinator)가 raw_log로 전환됐으므로 본 모듈은
# 잔존 호환 shim 없이 곧바로 폐기한다. import 시 즉시 오류로 경로 유출을 잡는다.
raise ImportError(
    "log_bus는 v3.3.0에서 폐기됐다 — raw_log.raw(tag, msg, to_tui=...) 단일 경로를 사용할 것."
)
