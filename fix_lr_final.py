import re

with open('chzzktube/pipeline/live_recorder.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the extra closing parenthesis and blank line in the except block
old = '''                except Exception as e:
                    
                )'''

new = '''                except Exception as e:
                    import chzzktube.core.raw_log as raw_log
                    raw_log.raw("LIVE", f"_drain_stderr error: {type(e).__name__}: {e}", is_error=True, to_tui=False)'''

if old in content:
    content = content.replace(old, new)
    with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed!')
else:
    print('Not found')
    idx = content.find('except Exception as e:')
    if idx >= 0:
        print('Found at:', idx)
        print(repr(content[idx:idx+100]))