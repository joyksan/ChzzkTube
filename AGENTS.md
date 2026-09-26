# Language & Communication Style

## Think Out Loud in Korean
- **ALWAYS** explain your reasoning, internal thoughts, and planned steps in **Korean** before executing any tool or command.
- Treat this as "thinking out loud" (e.g., "지금은 코드를 수정해야 하니까 `edit_file` 도구를 사용해서 오류를 고쳐보자...").
- Keep your internal monologue natural, developer-friendly, and concise.
- Even if you are interacting with English code or documentation, your internal process and commentary must remain in Korean.

#  FILE OPERATIONS & ANTI-HEREDOC CONSTRAINTS

## Strict Tool Usage for File Modification & Creation
- **NEVER** use the `bash` tool to create, modify, overwrite, or append contents to files.
- **NEVER** use terminal heredocs/redirects like `cat << 'EOF'`, `cat << 'PYEOF'`, `pyeof`, `sed`, `awk`, or `>` inside the `bash` tool.
- Running multiline scripts via raw bash input is strictly forbidden due to terminal syntax parsing and escape character bugs.

# PYTHON & ENVIRONMENT EXECUTION MANDATE (UV SSOT)
- **ALWAYS** run Python, Pytest, scripts, and package commands via `uv run` (e.g. `uv run pytest`, `uv run python main.py`, `uv run python sync_mirrors.py`).
- **NEVER** invoke bare `python` or bare `pytest` directly in the terminal to prevent PATH collision with global interpreters lacking project virtualenv dependencies (e.g. PySide6).

# FILE PERSISTENCE & DISK FLUSH INTEGRITY
- After editing or modifying files, verify that changes are physically flushed to disk via `git diff --stat` or `git status`.
- Do not assume in-memory editor buffers reflect on-disk state. If in-memory buffer stall occurs, enforce immediate disk write & flush.

# BUILT-IN TOOL MANDATE (7 CORE TOOLS ONLY)
You must strictly map your actions to the 7 built-in tools below. Do not assume or hallucinate legacy or non-existent tools.

### [FILE & CODEBASE MANIPULATION]
- **`editor`**: Use this **ONLY** to view file contents, create a new file from scratch, or completely overwrite an entire file.
- **`apply_patch`**: Use this **ALWAYS** when modifying specific parts of an existing file. You must provide a precise Unified Diff.
- **`read_files`**: Use this when you need to read multiple files simultaneously to understand context or perform code analysis.
- **`search`**: Use this to find specific keywords, function names, variables, or error targets across the entire project via ripgrep.

### [EXECUTION & ENVIRONMENT CONTROL]
- **`bash`**: Use this **ONLY** for running test suites, installing packages (npm, pip), building projects, or starting/stopping local servers. Do not use it for code input or text generation.

### [EXTERNAL RETRIEVAL & INTERACTION]
- **`fetch_web`**: Use this to send HTTP requests and fetch documentation or external web pages in parsed Markdown format.
- **`ask_question`**: Use this to ask for user confirmation, clarify ambiguous requirements, or request manual intervention before taking risky actions.


# Agent Skills Framework
You must strictly follow the engineering workflows in `.skills/`.
Do not take shortcuts, skip tests, or write code without understanding specifications.
Whenever a user command matches or the task context matches one of the skills below, **read that specific `SKILL.md` file using `read_file` FIRST** before proposing or executing code.

## Master Routing Table (25 Skills)

### 1. System & Meta 
- `/skills` -> Read `.skills/using-agent-skills/SKILL.md` (Skill orchestration, system initialization, and usage rules)

### 2. Specification & Planning
- `/spec` -> Read `.skills/spec-driven-development/SKILL.md` (Requirements & acceptance criteria)
- `/plan` -> Read `.skills/planning-and-task-breakdown/SKILL.md` (15-30m atomic task decomposition)
- `/idea` -> Read `.skills/idea-refine/SKILL.md` (Clarifying vague concepts)
- `/interview` -> Read `.skills/interview-me/SKILL.md` (Extract requirements via Q&A)
- `/api` -> Read `.skills/api-and-interface-design/SKILL.md` (Interface contracts & ergonomics)

### 3. Implementation & Testing
- `/build` -> Read `.skills/incremental-implementation/SKILL.md` (Slice-by-slice implementation)
- `/tdd` or `/test` -> Read `.skills/test-driven-development/SKILL.md` (Red-green-refactor)
- `/browser-test` -> Read `.skills/browser-testing-with-devtools/SKILL.md` (Console/network verification)
- `/ui` -> Read `.skills/frontend-ui-engineering/SKILL.md` (UI component states & accessibility)

### 4. Verification, Review & Security
- `/review` -> Read `.skills/code-review-and-quality/SKILL.md` (Strict 5-axis quality review)
- `/security` -> Read `.skills/security-and-hardening/SKILL.md` (Threat modeling & input sanitization)
- `/doubt` -> Read `.skills/doubt-driven-development/SKILL.md` (Challenging assumptions & edge cases)
- `/perf` -> Read `.skills/performance-optimization/SKILL.md` (Profiling & bottleneck mitigation)

### 5. Refactoring & Code Health
- `/simplify` -> Read `.skills/code-simplification/SKILL.md` (Removing over-engineering)
- `/debug` -> Read `.skills/debugging-and-error-recovery/SKILL.md` (Hypothesis-driven root cause)
- `/migrate` -> Read `.skills/deprecation-and-migration/SKILL.md` (Safe API deprecation)
- `/constraint` -> Read `.skills/constraint-driven-development/SKILL.md` (Strict boundaries)

### 6. Git, Ops & Shipping
- `/git` -> Read `.skills/git-workflow-and-versioning/SKILL.md` (Atomic commits & semver)
- `/cicd` -> Read `.skills/ci-cd-and-automation/SKILL.md` (Pipeline & action configurations)
- `/ship` -> Read `.skills/shipping-and-launch/SKILL.md` (Pre-flight checks & launch readiness)
- `/observe` -> Read `.skills/observability-and-instrumentation/SKILL.md` (Logs, metrics, telemetry)

### 7. Documentation & Agent Context
- `/docs` -> Read `.skills/documentation-and-adrs/SKILL.md` (ADRs & technical docs)
- `/context` -> Read `.skills/context-engineering/SKILL.md` (Managing context limits)
- `/sources` -> Read `.skills/source-driven-development/SKILL.md` (Grounding truth in official docs)
- Meta Skill -> Read `.skills/using-agent-skills/SKILL.md` (When unsure which skill to pick)



## Understand-Anything Architecture Skills
When the user triggers these commands or asks for repo mapping/analysis, read the corresponding SKILL.md before proceeding:

- `/understand`           -> Read `.skills/understand-anything/understand/SKILL.md` (Full architecture & knowledge graph)
- `/understand-dashboard` -> Read `.skills/understand-anything/understand-dashboard/SKILL.md` (Interactive visualization UI)
- `/understand-explain`   -> Read `.skills/understand-anything/understand-explain/SKILL.md` (Deep dive on specific module)
- `/understand-domain`    -> Read `.skills/understand-anything/understand-domain/SKILL.md` (Business processes & domain mapping)
- `/understand-diff`      -> Read `.skills/understand-anything/understand-diff/SKILL.md` (Impact analysis of code changes)
- `/understand-onboard`   -> Read `.skills/understand-anything/understand-onboard/SKILL.md` (Step-by-step developer tour)
- `/understand-chat`      -> Read `.skills/understand-anything/understand-chat/SKILL.md` (Context-aware codebase Q&A)
- `/understand-knowledge` -> Read `.skills/understand-anything/understand-knowledge/SKILL.md` (Document wiki/notes graph)
- `/understand-figma`     -> Read `.skills/understand-anything/understand-figma/SKILL.md` (UI design to code mapping)