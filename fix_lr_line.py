with open('chzzktube/pipeline/live_recorder.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix lines 241-244
new_lines = []
for i, line in enumerate(lines):
    # Fix the except block (lines 241-244 in 1-indexed)
    if i == 240:  # "                except Exception as e:" (0-indexed)
        new_lines.append(line)
    elif i == 241:  # blank line after except
        continue  # Skip blank line
    elif i == 242:  # the extra )
        continue  # Skip extra )
    else:
        new_lines.append(line)

with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Fixed!')