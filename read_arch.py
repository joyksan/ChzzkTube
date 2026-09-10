import os, io, sys

target = None
for entry in os.scandir('.'):
    if entry.is_file() and entry.name.endswith('.md'):
        try:
            name = entry.name.encode('utf-8').decode('utf-8')
        except UnicodeDecodeError:
            continue
        if '아키텍' in name or '구조' in name:
            target = entry.path
            break

if target is None:
    print('not found', file=sys.stderr)
    sys.exit(1)

with io.open(target, 'r', encoding='utf-8') as f:
    print(f.read())
