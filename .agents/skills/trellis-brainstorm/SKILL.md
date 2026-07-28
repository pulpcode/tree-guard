---
name: trellis-brainstorm
description: "Guides collaborative requirements discovery before implementation. Creates task directory, seeds PRD, asks high-value questions one at a time, researches technical choices, and converges on MVP scope. Use when requirements are unclear, there are multiple valid approaches, or the user describes a new feature or complex task."
---

# Brainstorm - Requirements Discovery (AI Coding Enhanced)

**CoreRule**: Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time.

If a question can be answered by exploring the codebase, explore the codebase instead.

---

Guide AI through collaborative requirements discovery **before implementation**, optimized for AI coding workflows:

* **Resume-or-task-first** (preserve continuity before creating anything)
* **Action-before-asking** (reduce low-value questions)
* **Research-first** for technical choices (avoid asking users to invent options)
* **Diverge → Converge** (expand thinking, then lock MVP)

---

## When to Use

Triggered from `trellis-start` when the user describes a development task,
especially when:

* requirements are unclear or evolving
* there are multiple valid implementation paths
* trade-offs matter (UX, reliability, maintainability, cost, performance)
* the user might not know the best options up front

---

## Core Principles (Non-negotiable)

1. **Resume-or-task-first (preserve continuity)**
   Inspect active tasks before creating one. Resume a unique matching task; otherwise
   create a task so the user's approved ideas can be recorded.

2. **Action before asking**
   If you can derive the answer from repo code, docs, configs, conventions, or quick research — do that first.

3. **One question per message**
   Never overwhelm the user with a list of questions. Ask one, update PRD, repeat.

4. **Prefer concrete options**
   For preference/decision questions, present 2–3 feasible, specific approaches with trade-offs.

5. **Research-first for technical choices**
   If the decision depends on industry conventions / similar tools / established patterns, do research first, then propose options.

6. **Diverge → Converge**
   After initial understanding, proactively consider future evolution, related scenarios, and failure/edge cases — then converge to an MVP with explicit out-of-scope.

7. **No meta questions**
   Do not ask "should I search?" or "can you paste the code so I can continue?"
   If you need information: search/inspect. If blocked: ask the minimal blocking question.

---

## Step 0: Resolve or Create the Task (ALWAYS)

Before any Q&A, run:

```bash
python3 ./.trellis/scripts/get_context.py
python3 ./.trellis/scripts/task.py current --source
```

- If the session pointer resolves a task, continue it.
- If the pointer is absent but exactly one active task assigned to the current
  developer matches the request, treat it as an explicit resume candidate and load
  `trellis-continue`.
- If zero tasks match, create one.
- If multiple tasks could match, ask for the exact task. Do not guess, create a
  duplicate, or edit `.trellis/.runtime/`.

When creation is needed:

* Use a **temporary working title** derived from the user's message.
* It's OK if the title is imperfect — refine later in PRD.

```bash
TASK_DIR=$(python3 ./.trellis/scripts/task.py create "brainstorm: <short goal>" --slug <auto>)
```

Use a slug without a date prefix. `task.py create` adds the `MM-DD-`
directory prefix automatically.

Create/seed `prd.md` immediately with what you know. Before writing, apply
`.trellis/spec/backend/development-data-boundary.md`: store only approved
external-development facts and fully fictional examples, never protected code,
trees, VALUE payloads, expert/model text, identifiers, credentials, or raw logs.

```markdown
# brainstorm: <short goal>

## Goal

<one paragraph: what + why>

## What I already know

* <facts from user message>
* <facts discovered from repo/docs>

## Assumptions (temporary)

* <assumptions to validate>

## Open Questions

* <ONLY Blocking / Preference questions; keep list short>

## Requirements (evolving)

* <start with what is known>

## Acceptance Criteria (evolving)

* [ ] <testable criterion>

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* `uv sync --frozen`, the configured `unittest` suite, and `git diff --check` pass
* Unconfigured lint/typecheck/coverage tools are not reported as passing
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* <what we will not do in this task>

## Technical Notes

* <files inspected, constraints, links, references>
* <research notes summary if applicable>
```

---

## Step 1: Auto-Context (DO THIS BEFORE ASKING QUESTIONS)

Before asking questions like "what does the code look like?", gather context yourself:

### Repo inspection checklist

* Identify likely modules/files impacted
* Locate existing patterns (similar features, conventions, error handling style)
* Check configs, scripts, existing command definitions
* Note any constraints (runtime, dependency policy, build tooling)

### Documentation checklist

* Look for existing PRDs/specs/templates
* Look for command usage examples, README, ADRs if any

Write findings into PRD:

* Add to `What I already know`
* Add constraints/links to `Technical Notes`

---

## Step 2: Classify Complexity (still useful, not gating task creation)

| Complexity   | Criteria                                               | Action                                      |
| ------------ | ------------------------------------------------------ | ------------------------------------------- |
| **Trivial**  | Single-line fix, typo, obvious change                  | Skip brainstorm, implement directly         |
| **Simple**   | Clear goal, 1–2 files, scope well-defined              | Ask 1 confirm question, then implement      |
| **Moderate** | Multiple files, some ambiguity                         | Light brainstorm (2–3 high-value questions) |
| **Complex**  | Vague goal, architectural choices, multiple approaches | Full brainstorm                             |

> Note: A matching task was resumed or created in Step 0. Classification only
> affects the depth of brainstorming.

---

## Step 3: Question Gate (Ask ONLY high-value questions)

Before asking ANY question, run the following gate:

### Gate A — Can I derive this without the user?

If answer is available via:

* repo inspection (code/config)
* docs/specs/conventions
* quick market/OSS research

→ **Do not ask.** Fetch it, summarize, update PRD.

### Gate B — Is this a meta/lazy question?

Examples:

* "Should I search?"
* "Can you paste the code so I can proceed?"
* "What does the code look like?" (when repo is available)

→ **Do not ask.** Take action.

### Gate C — What type of question is it?

* **Blocking**: cannot proceed without user input
* **Preference**: multiple valid choices, depends on product/UX/risk preference
* **Derivable**: should be answered by inspection/research

→ Only ask **Blocking** or **Preference**.

---

## Step 4: Research-first Mode (Mandatory for technical choices)

### Trigger conditions (any → research-first)

* The task involves selecting an approach, library, protocol, framework, template system, plugin mechanism, or CLI UX convention
* The user asks for "best practice", "how others do it", "recommendation"
* The user can't reasonably enumerate options

### Codex 内联研究

当前项目只维护 Codex，主代理直接完成研究并把经批准结论写入
`{TASK_DIR}/research/<topic>.md`。不要因任务存在 JSONL 就加载其中声明的路径。

从受保护环境使用 Web、MCP、插件或其他外部服务前，必须先审查将发送的准确
查询并严格脱敏。真实节点字段名、业务上下文、内部路径、错误原文、Prompt、
模型请求/响应和原始日志不得发给外部工具。不能安全改写时，只记录
“需要内网核验”。

研究步骤：

1. 从本外网仓库或已批准公开资料中识别 2–4 个可比模式；
2. 总结共同约定及原因；
3. 映射到本仓库的 MVP、确定性和数据边界；
4. 只把问题、范围、日期、公开/仓库相对依据、结论和限制写入
   `{TASK_DIR}/research/<topic>.md`；
5. 在 PRD 中提出 2–3 个可行方案，不复制原始工具输出。

### Research output format (PRD)

The PRD itself should only reference the persisted research files, not duplicate their content. Add a `## Research References` section pointing at `research/*.md`.

Optionally, add a convergence section with feasible approaches derived from the research:

```markdown
## Research References

* [`research/<topic-a>.md`](research/<topic-a>.md) — <one-line takeaway>
* [`research/<topic-b>.md`](research/<topic-b>.md) — <one-line takeaway>

## Research Notes

### What similar tools do

* ...
* ...

### Constraints from our repo/project

* ...

### Feasible approaches here

**Approach A: <name>** (Recommended)

* How it works:
* Pros:
* Cons:

**Approach B: <name>**

* How it works:
* Pros:
* Cons:

**Approach C: <name>** (optional)

* ...
```

Then ask **one** preference question:

* "Which approach do you prefer: A / B / C (or other)?"

---

## Step 5: Expansion Sweep (DIVERGE) — Required after initial understanding

After you can summarize the goal, proactively broaden thinking before converging.

### Expansion categories (keep to 1–2 bullets each)

1. **Future evolution**

   * What might this feature become in 1–3 months?
   * What extension points are worth preserving now?

2. **Related scenarios**

   * What adjacent commands/flows should remain consistent with this?
   * Are there parity expectations (create vs update, import vs export, etc.)?

3. **Failure & edge cases**

   * Conflicts, offline/network failure, retries, idempotency, compatibility, rollback
   * Input validation, security boundaries, permission checks

### Expansion message template (to user)

```markdown
I understand you want to implement: <current goal>.

Before diving into design, let me quickly diverge to consider three categories (to avoid rework later):

1. Future evolution: <1–2 bullets>
2. Related scenarios: <1–2 bullets>
3. Failure/edge cases: <1–2 bullets>

For this MVP, which would you like to include (or none)?

1. Current requirement only (minimal viable)
2. Add <X> (reserve for future extension)
3. Add <Y> (improve robustness/consistency)
4. Other: describe your preference
```

Then update PRD:

* What's in MVP → `Requirements`
* What's excluded → `Out of Scope`

---

## Step 6: Q&A Loop (CONVERGE)

### Rules

* One question per message
* Prefer multiple-choice when possible
* After each user answer:

  * Update PRD immediately
  * Move answered items from `Open Questions` → `Requirements`
  * Update `Acceptance Criteria` with testable checkboxes
  * Clarify `Out of Scope`

### Question priority (recommended)

1. **MVP scope boundary** (what is included/excluded)
2. **Preference decisions** (after presenting concrete options)
3. **Failure/edge behavior** (only for MVP-critical paths)
4. **Success metrics & Acceptance Criteria** (what proves it works)

### Preferred question format (multiple choice)

```markdown
For <topic>, which approach do you prefer?

1. **Option A** — <what it means + trade-off>
2. **Option B** — <what it means + trade-off>
3. **Option C** — <what it means + trade-off>
4. **Other** — describe your preference
```

---

## Step 7: Propose Approaches + Record Decisions (Complex tasks)

After requirements are clear enough, propose 2–3 approaches (if not already done via research-first):

```markdown
Based on current information, here are 2–3 feasible approaches:

**Approach A: <name>** (Recommended)

* How:
* Pros:
* Cons:

**Approach B: <name>**

* How:
* Pros:
* Cons:

Which direction do you prefer?
```

Record the outcome in PRD as an ADR-lite section:

```markdown
## Decision (ADR-lite)

**Context**: Why this decision was needed
**Decision**: Which approach was chosen
**Consequences**: Trade-offs, risks, potential future improvements
```

---

## Step 8: Final Confirmation + Implementation Plan

When open questions are resolved, confirm complete requirements with a structured summary:

### Final confirmation format

```markdown
Here's my understanding of the complete requirements:

**Goal**: <one sentence>

**Requirements**:

* ...
* ...

**Acceptance Criteria**:

* [ ] ...
* [ ] ...

**Definition of Done**:

* ...

**Out of Scope**:

* ...

**Technical Approach**:
<brief summary + key decisions>

**Implementation Plan (small PRs)**:

* PR1: <scaffolding + tests + minimal plumbing>
* PR2: <core behavior>
* PR3: <edge cases + docs + cleanup>

Does this look correct? If yes, I'll proceed with implementation.
```

### Subtask Decomposition (Complex Tasks)

For complex tasks with multiple independent work items, create subtasks:

```bash
# Create child tasks
CHILD1=$(python3 ./.trellis/scripts/task.py create "Child task 1" --slug child1 --parent "$TASK_DIR")
CHILD2=$(python3 ./.trellis/scripts/task.py create "Child task 2" --slug child2 --parent "$TASK_DIR")

# Or link existing tasks
python3 ./.trellis/scripts/task.py add-subtask "$TASK_DIR" "$CHILD_DIR"
```

---

## PRD Target Structure (final)

`prd.md` should converge to:

```markdown
# <Task Title>

## Goal

<why + what>

## Requirements

* ...

## Acceptance Criteria

* [ ] ...

## Definition of Done

* ...

## Technical Approach

<key design + decisions>

## Decision (ADR-lite)

Context / Decision / Consequences

## Out of Scope

* ...

## Technical Notes

<constraints, references, files, research notes>
```

---

## Anti-Patterns (Hard Avoid)

* Asking user for code/context that can be derived from repo
* Asking user to choose an approach before presenting concrete options
* Meta questions about whether to research
* Staying narrowly on the initial request without considering evolution/edges
* Letting brainstorming drift without updating PRD

---

## Integration with Start Workflow

After brainstorm completes (Step 8 confirmation approved), continue inside the
Task Workflow's **Phase 1: Plan**, then enter Phase 2:

```text
Brainstorm
  Step 0: Create task directory + seed PRD
  Step 1–7: Discover requirements, research, converge
  Step 8: Final confirmation → user approves
  ↓
Task Workflow Phase 1 (Plan)
  → Select applicable specs from fixed indexes
  → Do not curate or load arbitrary JSONL paths
  → Activate task with task.py start
  ↓
Task Workflow Phase 2 (Execute)
  trellis-before-dev → Implement → trellis-check
  ↓
Task Workflow Phase 3 (Finish)
  Verify → Update specs if needed → Commit with approval → Archive separately
```

The task directory and PRD already exist, but Phase 1 context selection and activation
are still required. Do not skip directly to implementation.

---

## Related entry points

| Entry point | When to use |
|---------|-------------|
| `trellis-start` skill | Re-establish session context and route into brainstorm |
| `trellis-finish-work` skill | After reviewed implementation is committed |
| `trellis-update-spec` skill | When durable project conventions emerge |
