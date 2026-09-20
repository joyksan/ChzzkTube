#!/usr/bin/env python3
import re

line = '[07:43:15] DEPS  │ FAIL  │ FFMP  │ binary incompatible → retry mirror (1/3)'
print("Input line:", repr(line))

# Current pattern in test
pattern = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] (SYS|DEPS|ANAL|DL|LIVE|MERG|BATCH|POT)│ (READY|RUN|OK|DONE|SKIP|WARN|FAIL|ABORT|END)│ [\w\s]+ \| .+$")
result = pattern.match('[07:37:43] DEPS  │ FAIL  │ FFMP  │ binary incompatible → retry mirror (1/3)')
print("Test 1 (with │):", pattern.match('[07:37:43] DEPS  │ FAIL  │ FFMP  │ binary incompatible → retry mirror (1/3)'))

# The actual separator is " │ " (space + box char + space)
# The box drawing char is │ (U+2502)
# The pattern should match " │ " (space + box char + space)
pattern2 = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] (SYS|DEPS|ANAL|DL|LIVE|MERG|BATCH|POT)\s*│\s*(READY|RUN|OK|DONE|SKIP|WARN|FAIL|ABORT|END)\s*│\s*[\w\s]+ │ .+$")
print("Test 2:", pattern2.match('[07:37:43] DEPS  │ FAIL  │ FFMP  │ binary incompatible → retry mirror (1/3)'))

# Let's check what the actual line looks like
print("Line:", repr('[07:37:43] DEPS  │ FAIL  │ FFMP  │ binary incompatible → retry mirror (1/3)'))
print("Has │:", '│' in '[07:37:43] DEPS  │ FAIL  │ FFMP  │ binary incompatible → retry mirror (1/3)')
print("Has |:", '|' in '[07:37:43] DEPS  │ FAIL  │ FFMP  │ binary incompatible → retry mirror (1/3)')]