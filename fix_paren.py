with open('chzzktube/pipeline/live_recorder.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and fix the problematic lines
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    # Check for the problematic pattern: blank line followed by single )
    if (i > 0 and lines[i-1].strip() == '' and 
        line.strip() == ')' and 
        i > 1 and 'except Exception as e:' in lines[i-2]):
        print(f'Fixing line {i+1}: removing extra )')
        i += 1  # Skip this line
        continue
    new_lines.append(line)
    i += 1

with open('chzzktube/pipeline/live_recorder.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Fixed extra closing parenthesis!')