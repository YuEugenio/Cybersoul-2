# Chapter 3: Prompt System — The Agent's Persistent Personality

> **Core question**: You spent an hour shaping the AI into exactly what you wanted — the style, the rules, the preferences all dialed in. The next day you open a new conversation and it's back to factory defaults. How can an Agent "remember who it is"?

---

This is not a matter of the AI being insufficiently intelligent. It is the inevitable consequence of prompts and conversations sharing the same lifecycle.

When the conversation ends, the prompt dissolves. The style you spent time establishing, the rules you agreed on, the configuration you accumulated — all reset to zero. The next time you start over, it is always day one. The deeper problem is: even when a particular tuning session works well, you cannot explain why. Which sentence made the difference? Which constraint played the decisive role? Without records, without structure, there is no reproducible knowledge.

This is an **engineerable** problem, not merely an efficiency problem. A process that cannot be reproduced cannot be shared across a team, cannot be systematically improved, and cannot be traced when something goes wrong.

OpenClaw's solution strikes at the root: **write prompts into files and keep them permanently**. This sounds like a trick; in practice it is a paradigm shift — the Agent's identity now exists independently of any single conversation, subject to version control, team collaboration, and continuous accumulation.

---

## I. The Dilemma of Temporary Instructions

This section explains: the problem with traditional prompts is structural, not a matter of personal skill.

Compressing all configuration into a single system prompt injected at the start of a conversation has been the standard practice of "prompt engineering" for the past decade. It appears adequate on the surface, but three hidden problems have never been resolved:

| Problem | How it manifests | Root cause |
|---------|-----------------|------------|
| Temporariness | Disappears when the conversation ends; starts from zero every time | Prompt and conversation share the same lifecycle |
| Not engineerable | Cannot be reproduced; unclear which parts had an effect | No structure; no way to modify a single layer in isolation |
| Hard to collaborate on | No way to trace who changed what, or why | A block of private text with no version history |

All three problems share the same root cause: **prompts are temporary**.

OpenClaw's solution is a decoupling: it separates the Agent's identity from the conversation lifecycle, writes it into files, and lets it exist independently.

```
Traditional approach:
  Conversation starts ──→ User inputs prompt ──→ AI responds ──→ Prompt dies with the conversation

OpenClaw approach:
  ┌──────────────────────────────────────┐
  │  SOUL.md / USER.md / AGENTS.md ...  │  ← Persists permanently, independent of conversations
  └─────────────────┬────────────────────┘
                    ↓ Automatically read and dynamically assembled before each inference
  Each conversation ─────────→ System prompt ──→ AI responds
```

The significance of this difference goes beyond "convenience." Files can be version-controlled with Git. You can see the difference between the configuration from three months ago and today's, understand why you made that change at the time, and reuse a battle-tested configuration in a new project — all of which were impossible in the era when "prompts are temporary text."

---

## II. Configuration as Personality: The 8-File Architecture

This section answers: what each of the 8 files is, and why the division is structured this way.

Breaking a monolithic "catch-all" prompt into eight files is not just "tidier" — it introduces **addressability** to configuration: when behavior is anomalous you know where to look for the cause; when you want to adjust something you know which file to change and what it will affect.

### Overview

| File | Plain-language analogy | Core purpose |
|------|----------------------|--------------|
| `SOUL.md` | **Persona and personality** | Defines "who I am" — character, values, guiding principles |
| `USER.md` | **Contact card and profile** | Defines "who you are" — user profile, preferences, interaction history |
| `AGENTS.md` | **Operational capabilities** | Defines "how I work" — workflows, decision rules |
| `TOOLS.md` | **Toolbox** | Defines "what tools I have" — environment configuration, resource mappings |
| `IDENTITY.md` | **ID / business card** | Defines the Agent's identity markers and basic attributes |
| `MEMORY.md` | **Notebook / experience log** | Defines "what I remember" — fact store, accumulated insights |
| `HEARTBEAT.md` | **Alarm / schedule** | Defines "when I act" — scheduled tasks, trigger conditions |
| `BOOTSTRAP.md` | **Factory defaults** | Initial bootstrap configuration for a new workspace |

The eight files cover every dimension an Agent needs to operate: **who it is** (SOUL, IDENTITY), **whom it serves** (USER), **how it works** (AGENTS), **what tools it has** (TOOLS), **what it remembers** (MEMORY), **how it acts proactively** (HEARTBEAT), and **how it initializes** (BOOTSTRAP). No redundancy, no gaps.

### SOUL.md and AGENTS.md: Separating Personality from Rules

LLMs have one structural characteristic: they "guess" the role they should play based on the type of question — expert for technical questions, friend for everyday questions, expansive creative partner for imaginative questions. This **role drift** is a side effect of the LLM's powerful capabilities, but for an Agent that requires predictable behavior it is fatal. `SOUL.md` is placed at the highest priority in the system prompt for a single purpose: regardless of how context shifts, lock in the role and prevent drift.

```
SOUL.md answers "what kind of entity is this Agent":
  "I am a security-focused systems engineer who defaults to conservative action under uncertainty."
  → Values and beliefs; cannot be overridden by user requests; the underlying operating system

AGENTS.md answers "how does this Agent work":
  "On receiving a deployment request: check coverage → confirm env vars
   → send confirmation message → wait for approval → execute deployment"
  → Decision processes and operational standards; can be adjusted per scenario
```

Personality determines "how to think"; rules determine "how to act." Only by separating the two can each be optimized independently.

### USER.md and MEMORY.md: Two Different Kinds of "Knowing You"

These two files are often confused, but they describe entirely different information:

```
USER.md (what kind of person you are — static profile)
──────────────────────────────────────────────────────
  Technical level: intermediate developer
  Preference: concise and direct, no padding
  Language: Chinese preferred

MEMORY.md (what we have been through together — dynamic accumulation)
─────────────────────────────────────────────────────────────────────
  2026-03-10: Confirmed using pnpm, not npm
  2026-03-12: Must run db:migrate before deploying
  Phoenix Project = Client X's e-commerce rebuild project
```

USER.md is a relatively stable user profile; MEMORY.md is a growing record of shared experience accumulated through use. Conflating the two causes USER.md to grow longer and harder to maintain over time.

USER.md is not purely static. When a user says "reply in Chinese" during a conversation, the Agent will proactively write "language preference: Chinese" into USER.md after completing the task — that preference is then persisted and need not be stated again next time. This mechanism lets the user profile refine itself automatically through actual usage.

**TOOLS.md** is an environment reference — server addresses, project paths, credential locations. It does not control "which tools are available"; it tells the Agent "where I am working," locking in the environmental information that would be impossible to communicate verbally every time.

For example: you ask the Agent to "deploy to the test server." The Agent has deployment capability, but does not know the test server's IP, username, or key location. TOOLS.md locks in that environmental information so the Agent does not need to be told each time — it retrieves it directly from "memory."

**MEMORY.md** accumulates continuously through use. Its write strategy is **"silent refresh as the primary mode, explicit instruction as the secondary mode"**: when a conversation grows long and the system needs to compress context, the Agent automatically writes important information into MEMORY.md in the background — silently, without interrupting your workflow. You can also tell the Agent "remember this" at any time and it will write immediately.

**HEARTBEAT.md** defines periodic check-lists. Most Agents are reactive; HEARTBEAT.md evolves the Agent from a "question-answering machine" into a "proactive collaborator."

**BOOTSTRAP.md** is loaded only once after a workspace is created, then archived after bootstrapping completes — initialization logic should not remain in the system indefinitely.

---

## III. How the System Works

This section answers: how configuration files are read and assembled, and three key mechanisms.

### Priority Layering

Every time you send a message, before the Agent reasons, the system re-reads all configuration files and dynamically assembles the system prompt:

```
System prompt (top to bottom, priority decreasing):
┌──────────────────────────────────────┐
│  Tool definitions (list of tools)    │ ← Always first; safety boundaries cannot be overridden
│  Safety guardrails                   │
│  Skill list (name+description+path,  │ ← Index only; loaded on demand
│              not full text)          │
│  Working directory information        │
│  Contents of the eight config files  │ ← SOUL / USER / AGENTS / TOOLS / ...
│  Sandbox restrictions (if enabled)   │
│  Current time                        │ ← Always last; lowest priority
└──────────────────────────────────────┘
```

Content higher in the list is harder to override by content lower down. This ordering is also a debugging guide: when behavior produces unexpected results, trace the priority chain from top to bottom — far more tractable than staring at a block of mixed text with no idea where to start.

Each configuration file has a size limit (`bootstrapMaxChars` defaults to 20,000 characters); content exceeding the limit is truncated from the **tail**. This implies an iron rule for writing configuration: **put the most important content at the top of the file**.

### Hot Reload

Edit a file, save it, send the next message — the new configuration takes effect immediately. No restart, no deployment, no waiting.

For example, if you change the Agent's name in `SOUL.md` from "Alex" to "Jordan" and send the next message, it is already Jordan. No restart, no redeployment needed — this is what hot reload means for personality configuration: edit and it is live.

This works through **file fingerprint comparison**:

```
Initial load:
  Read file contents → Record fingerprint (path + size + modification time) → Store in cache

Before each subsequent conversation:
  Quickly compare old and new fingerprints
    ├── Fingerprints match ──→ Use cache directly (zero overhead)
    └── Fingerprint changed ──→ Re-read file; new configuration takes effect immediately
```

When files have not changed, overhead is virtually zero; when a file changes, it is detected immediately. The deeper value: hot reload transforms Agent tuning from a waterfall cycle of "edit → deploy → test → edit" into a real-time feedback loop of "edit → see the effect → edit."

### Token Budget and Lazy Skill Loading

Skill files (`skills/*.md`) are not injected in full — only a one-line index entry is injected:

```
.agents/
├── skills/
│   ├── deploy-app/
│   │   └── SKILL.md
│   ├── run-tests/
│   │   └── SKILL.md
│   └── code-review/
│       └── SKILL.md
```

```
System prompt (index section):
  deploy-app: Deploy the application to the target environment  [path: skills/deploy-app.md]
  run-tests:  Run tests and generate a report                   [path: skills/run-tests.md]
        │ When the Agent determines it needs a particular skill
        ↓
  Proactively uses the read tool to fetch the full skill text (on demand)
```

The base prompt stays lean while supporting dozens of skills coexisting without blowing up the context. Whether you have 5 skills or 50, the index section remains nearly the same size.

---

## IV. Markdown: The Lowest-Cost Engineering Bridge

This section answers: why Markdown, and not JSON, YAML, or code.

The choice of Markdown was not accidental; it simultaneously satisfies the needs of three different roles:

| Role | Need | Markdown's advantage |
|------|------|---------------------|
| Human author | Intuitive to read, low barrier to edit | WYSIWYG; no configuration syntax to learn |
| Git version control | Text file, diff-comparable | Prompts have a commit history for the first time |
| LLM reader | Primary format of training data | Models understand Markdown structure natively |

Writing configuration in JSON has a high reading cost for humans; writing it in code raises the barrier further and introduces the risk of executing logic. Markdown is the lowest common denominator all three can accept — humans can edit it directly, Git can track changes, and LLMs can understand it accurately.

This also means Agent configuration has **a traceable history** for the first time. When you commit a change to SOUL.md with a note explaining why, you will still be able to understand that decision three months later. In the era when "prompts are temporary text," this was completely impossible.

Writing good configuration files comes down to one core principle: **specific beats abstract**.

```
❌ Vague: "Please act cautiously"
   → The interpretation of "cautiously" is left to the model; behavior is unpredictable

✅ Specific: "Before executing any delete operation, list the affected file paths,
             then wait for me to reply 'confirm' before proceeding"
   → Defines observable behavior; results are predictable
```

Good configuration is not documentation written for humans to read — it is instructions that leave the model no ambiguity about what to do in any given situation.

---

## Summary

| Core capability | How it is implemented |
|----------------|-----------------------|
| Persistent personality | 8 Markdown files exist independently of any conversation |
| Clear responsibilities | Each file has a single responsibility; anomalous behavior is locatable |
| Controllable priority | System prompt assembly order is fixed; SOUL is always first |
| Instant effect | File fingerprint caching; changes reflected in the very next message |
| Precise context | Truncation from the tail; skills loaded on demand; no wasteful bulk loading |
| Version-controllable | Markdown + Git; prompts have a history for the first time |

The Agent's growth is now an accumulating asset, not a temporary state that resets to zero at the end of every conversation. You are both the user and the cultivator — each iteration of configuration is one step of distillation from tacit knowledge into explicit engineering.


---

→ [Chapter 4: Tool System](../chapter4/index.md)
