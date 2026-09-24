import re

with open('chzzktube/pipeline/live_recorder.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Remove the extra .strip(), and closing parens after the exception handler
old = '''raw_log.raw("LIVE", f"_drain_stderr error: {type(e).__name__}: {e}", is_error=True, to_tui=False).strip(),
                                      ),
'''

new = ''

if old in content:
    content = content.replace(old, new)
    with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed indentation!')
else:
    print('Old text not found, searching...')
    idx = content.find('raw_log.raw("LIVE", f"_drain_stderr error:')
    if idx >= 0:
        print(repr(content[idx:idx+150]))