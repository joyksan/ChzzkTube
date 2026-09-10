import os

for entry in os.scandir('.'):
    if entry.is_file() and entry.name.endswith('.md'):
        try:
            name = entry.name.encode('utf-8').decode('utf-8')
        except UnicodeDecodeError:
            continue
        if '아키텍' in name or '구조' in name:
            print(repr(entry.name))
            print('path=', entry.path)
