import chzzktube.core.raw_log as raw_log
events = []
raw_log.subscribe_concise(lambda ev, is_status, is_error: events.append(ev))
from chzzktube.control.startup_coordinator import StartupCoordinator
from unittest.mock import Mock
c = StartupCoordinator(Mock())
c._on_pot_status('staged')
import time
deadline = time.time() + 2.0
while time.time() < deadline and not events:
    time.sleep(0.02)
ev = events[-1]
print('stage:', repr(ev.stage), 'scope:', repr(ev.scope))