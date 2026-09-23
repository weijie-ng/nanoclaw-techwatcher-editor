# Authoring a subagent brief

This directory holds NanoClaw's **trunk-owned subagent briefs**: one Markdown file
per agent (`planner`, `general`, `fact-checker`, `refuter`, `verifier`, …). Each is
a YAML-frontmatter-plus-body definition that the Claude Agent SDK loads and the
orchestrator invokes through the `Agent` tool.

`syncSharedAgents` (`src/container-runner.ts`) copies every `*.md` here into each
group's `.claude/agents/` on container spawn (tracked in `.shared.json`); a group's
own briefs sit alongside and are left alone. So **editing a file here is a trunk
change**, it reaches every group on that group's next respawn, and the conformance
test (`src/container-runner.test.ts` → `syncSharedAgents`) derives the roster from
this directory, so a new file is picked up automatically.

This guide is the de-facto template the existing briefs share, reconciled with the
official Claude Code subagent docs (sources at the bottom). Where NanoClaw diverges
from the generic advice on purpose, it says so.

## Frontmatter

The core keys are `name`, `description` and `model` below, plus the scoping keys
`disallowedTools` / `tools` (see Tool scoping). The SDK supports more (`effort`,
`permissionMode`, `skills`, `maxTurns`, `mcpServers`, `memory`, …): see
`docs/SDK_DEEP_DIVE.md` for the full `AgentDefinition` schema.

- **`name`** (required): lowercase-with-hyphens, and **must match the filename**
  (`verifier.md` → `name: verifier`). The sync and its test key on it.
- **`description`** (required): the routing signal. Shape it as *what it does · what
  to give it · use it to fan out over items · **do not** use it for Z, which is
  `sibling-agent`*. The when-**not** half, naming the sibling that owns the excluded
  work, is what stops a caller mis-routing across the roster. (Generic Claude Code
  advises "use proactively" trigger phrasing for autonomous delegation; our agents
  are explicitly routed by an orchestrator or the `planner`, so the when/when-not +
  sibling routing matters more than proactive phrasing.)
- **`model`** (optional): **omit to inherit the group's model**; that is the default
  and the right choice for most. Pin only when a tier is genuinely intended: a cheap
  model for a narrow mechanical agent (`verifier` → `claude-haiku-4-5-20251001`), or a
  specific tier for a specialised one (`planner` → `claude-opus-4-8`). A family alias
  (`haiku`, `opus`) or a full ID both resolve; a cross-provider pin (`refuter` →
  `gemini-flash`) resolves through the OneCLI gateway.

## Body (the system prompt)

The markdown after the frontmatter is the agent's system prompt. Every brief follows
this skeleton, and the order matters:

1. **Role + the return-value contract.** Open with what the agent does, then:
   *"Your final message is the return value your caller reads: no preamble, no
   narration, no offer to continue."* In NanoClaw the final message **is the data the
   orchestrator ingests** (it is never shown to a human), so this contract is
   load-bearing, not the generic "output format" note.
2. **What you were given**: the inputs, and "state the assumption you took and carry
   on" rather than stopping to ask (a question costs the caller a whole round trip).
3. **How to work / check**: the method, the tools, the discipline.
4. **What is not yours**: hand-back routing to the sibling specialists (the body-side
   counterpart of the description's when-not).
5. **What to return**: a fenced block with the fixed return shape. **This is the most
   important section**: the caller only ever sees this.
6. **Rules**: the do/don'ts, closing with *"Write British English and do not use em
   dashes."*

## NanoClaw conventions (beyond the generic advice)

- **Return data, not prose.** The final message is parsed by the caller, not read by a
  person. Keep it to findings in the fixed shape.
- **Context isolation is half the reason to exist.** An agent absorbs output the
  orchestrator does not need to keep (searches, scrapes, a file to check) and hands
  back only the verdict or findings. Tell it to fan out over **items**, one agent per
  item, never one agent walking a list, and never to build the deliverable inside a
  worker that cannot see the rest.
- **Single responsibility.** One job per brief; route the rest to a sibling. Do not
  combine "research, verify, deliver" into one agent.
- **British English, no em dashes.** House rule, enforced by the closing line, applies
  to the brief itself too.

## Tool scoping

Least-privilege, but the mechanism depends on whether the agent's tool needs are
fixed. **These briefs are group-agnostic**, so the choice is not cosmetic: a group
wires its own capability MCP servers (`tavily`, `youtube`, a custom one), and a worker
is expected to call them (a real plan routed `general` to `mcp__youtube__youtube_channel`).

- **Broad workers use a denylist.** Every research/analysis brief (and `planner`)
  carries `disallowedTools: mcp__nanoclaw`. That strips the whole built-in host server
  (`send_message`, `send_file`, `ask_user_question`, tasks, self-mod, topics, `ncl`) so
  a worker cannot message, deliver, schedule or reconfigure, enforcing every brief's
  "return findings, do not act" boundary. It leaves the generic tools **and** any
  group-wired capability MCP server intact. **Do not** give these an allow-list: a
  `tools:` line that omits `mcp__*` silently strips whatever MCP server a group wired,
  and the trunk cannot know that config.
- **A genuinely narrow agent uses an allow-list.** `verifier` runs fixed mechanical
  checks and never touches capability MCP or messaging, so it pins
  `tools: Read, Write, Bash, Glob, Grep, Skill`. Only reach for `tools:` when the whole
  tool set is known and small; otherwise deny the host server and stop there.

Consider `effort: low` for the narrow agents too, and keep the prose boundaries
regardless of the frontmatter.

## Skill scoping (held, deliberately)

`skills:` frontmatter is a **silent context filter**: unlisted skills are hidden from
the agent with no error (SDK `sdk.d.ts`). Two reasons it is not applied across the
roster: this SDK build's parsing of a file-frontmatter `skills:` key is unconfirmed,
and over-scoping breaks an agent invisibly. A broad worker like `general` needs nearly
every skill, so scoping it is counterproductive anyway. If you scope skills on a
genuinely narrow agent, confirm at runtime that the filter takes effect and that the
agent can still reach every skill it uses before relying on it.

## Before you commit a new brief

- [ ] `name` matches the filename, lowercase-hyphen.
- [ ] `description` has both when-to-use and when-not (naming the sibling).
- [ ] `model` omitted (inherit) unless a tier is genuinely intended.
- [ ] Body opens with the return-value contract and ends with the British-English line.
- [ ] A fenced `What to return` block with a fixed shape.
- [ ] No em dashes anywhere in the brief.
- [ ] `pnpm exec vitest run src/container-runner.test.ts -t syncSharedAgents` passes
      (it auto-includes the new file).

## Sources

- Official Claude Code subagents: https://code.claude.com/docs/en/sub-agents.md
  (plus `agent-loop`, `agent-teams`, `agent-sdk/custom-tools` for the full field set)
- `docs/SDK_DEEP_DIVE.md`: the `AgentDefinition` schema as this install pins it
