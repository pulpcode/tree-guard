---
name: trellis-break-loop
description: "Deep bug analysis to break the fix-forget-repeat cycle. Analyzes root cause category, why fixes failed, prevention mechanisms, and captures knowledge into specs. Use after fixing a bug to prevent the same class of bugs."
---

# Break the Loop - Deep Bug Analysis

When debug is complete, use this for deep analysis to break the "fix bug -> forget -> repeat" cycle.

Before recording any example, trace, or lesson, apply
`.trellis/spec/backend/development-data-boundary.md`. Use fixed public codes,
aggregate facts, and fictional examples; do not preserve protected inputs, model
traffic, identifiers, paths, or raw diagnostics.

---

## Analysis Framework

Analyze the bug you just fixed from these 5 dimensions:

### 1. Root Cause Category

Which category does this bug belong to?

| Category | Characteristics | Example |
|----------|-----------------|---------|
| **A. Missing Spec** | No documentation on how to do it | New feature without checklist |
| **B. Cross-Layer Contract** | Interface between layers unclear | API returns different format than expected |
| **C. Change Propagation Failure** | Changed one place, missed others | Changed function signature, missed call sites |
| **D. Test Coverage Gap** | Unit test passes, integration fails | Works alone, breaks when combined |
| **E. Implicit Assumption** | Code relies on undocumented assumption | Timestamp seconds vs milliseconds |

### 2. Why Fixes Failed (if applicable)

If you tried multiple fixes before succeeding, analyze each failure:

- **Surface Fix**: Fixed symptom, not root cause
- **Incomplete Scope**: Found root cause, didn't cover all cases
- **Verification Gap**: search scope or configured checks did not cover it
- **Mental Model**: Kept looking in same layer, didn't think cross-layer

### 3. Prevention Mechanisms

What mechanisms would prevent this from happening again?

| Type | Description | Example |
|------|-------------|---------|
| **Documentation** | Write it down so people know | Update thinking guide |
| **Architecture** | Make the error impossible structurally | Type-safe wrappers |
| **Contract** | Deterministic validation and strict boundary shapes | Invalid artifact fails with a fixed code |
| **Runtime** | Safe diagnostics and explicit state transitions | Detect incomplete replay state |
| **Test Coverage** | Unit and integration tests | Verify the full affected flow |
| **Code Review** | Checklist, PR template | "Did you check X?" |

### 4. Systematic Expansion

What broader problems does this bug reveal?

- **Similar Issues**: Where else might this problem exist?
- **Design Flaw**: Is there a fundamental architecture issue?
- **Process Flaw**: Is there a development process improvement?
- **Knowledge Gap**: Is the team missing some understanding?

### 5. Knowledge Capture

Solidify insights into the system:

- [ ] Update `.trellis/spec/guides/` thinking guides
- [ ] Update relevant `.trellis/spec/` docs
- [ ] Create issue record (if applicable)
- [ ] Create feature ticket for root fix
- [ ] Update check guidelines if needed

---

## Output Format

Please output analysis in this format:

```markdown
## Bug Analysis: [Short Description]

### 1. Root Cause Category
- **Category**: [A/B/C/D/E] - [Category Name]
- **Specific Cause**: [Detailed description]

### 2. Why Fixes Failed (if applicable)
1. [First attempt]: [Why it failed]
2. [Second attempt]: [Why it failed]
...

### 3. Prevention Mechanisms
| Priority | Mechanism | Specific Action | Status |
|----------|-----------|-----------------|--------|
| P0 | ... | ... | TODO/DONE |

### 4. Systematic Expansion
- **Similar Issues**: [List places with similar problems]
- **Design Improvement**: [Architecture-level suggestions]
- **Process Improvement**: [Development process suggestions]

### 5. Knowledge Capture
- [ ] [Documents to update / tickets to create]
```

---

## Core Philosophy

> **The value of debugging is not in fixing the bug, but in making this class of bugs never happen again.**

Three levels of insight:
1. **Tactical**: How to fix THIS bug
2. **Strategic**: How to prevent THIS CLASS of bugs
3. **Philosophical**: How to expand thinking patterns

30 minutes of analysis saves 30 hours of future debugging.

---

## After Analysis: Immediate Actions

**IMPORTANT**: After completing the analysis above, you MUST immediately:

1. **Update spec/guides** - Don't just list TODOs, actually update the relevant files:
   - If it's a cross-platform issue → update `cross-platform-thinking-guide.md`
   - If it's a cross-layer issue → update `cross-layer-thinking-guide.md`
   - If it's a code reuse issue → update `code-reuse-thinking-guide.md`
   - If it's domain-specific → update the relevant `.trellis/spec/backend/*.md`

2. **Verify the local contract** - Re-read the affected spec index and run the
   repository checks declared in `.trellis/spec/backend/quality-guidelines.md`.
   TreeGuard has no separate upstream template directory to synchronize.

3. **Present the changes for review** - Do not stage or commit spec updates without
   explicit user approval. If an active task exists, keep the sanitized retrospective
   in that task rather than only in chat.

> The durable output is a reviewed local spec or task artifact, not an unreviewed
> transcript.
