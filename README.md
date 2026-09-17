# qa-testpacks — a known-defect corpus for the ThunderAy QA Agent

A deliberately broken Minecraft Bedrock add-on, used to measure what the QA Agent
actually catches. Every variant is one branch differing from `main` by exactly one
defect, so a run's findings are attributable to a single known cause.

This exists to answer Milestone 1's question — *"how good is it?"* — with a number.

## Layout

```
behavior_packs/qatp/     3 items, 2 blocks
resource_packs/qatp/     textures + atlases
ground-truth.json        machine-readable defect manifest (the scorer reads this)
package.json             `mcaddon` script → dist/qatp.mcaddon
```

The pack is data-only: no scripts, no dependencies. `bun install` is a no-op and
the build is a `zip`. It is deliberately tiny — five checklist ids — because every
id costs an engagement, a screenshot and a share of a judge call. A 200-item
fixture would multiply the cost of the benchmark without improving it.

## Running it

```bash
qa build <owner>/qa-testpacks --full --bench --ref main
qa build <owner>/qa-testpacks --full --bench --ref bug/hard-invisible-block
```

`--full` re-proves the whole checklist instead of carrying cached PASSes.
`--bench` passes an empty `priorKnowledge` so run N is not told to stay quiet
about what run N-1 found. **Without `--bench` the repeatability measurement is
meaningless** — the agent is instructed not to re-report known findings, so runs
2 and 3 go quiet and it reads as catastrophic inconsistency when it is designed
behaviour.

Run each variant **three times**. One run tells you nothing about consistency.

## The variants

| Branch | Tier | Defect | Catchable by |
|---|---|---|---|
| `main` | control | none — anything reported is a false positive | — |
| `bug/easy-missing-texture` | easy | `qatp:ruby` icon → missing texture checker | vision |
| `bug/medium-wrong-texture` | medium | `qatp:marker_block` wears the lamp's texture | vision |
| `bug/hard-invisible-block` | hard | `qatp:marker_block` places but draws nothing | vision only |
| `bug/hard-no-light` | hard | `qatp:lamp_block` emits no light | needs the contract |
| `bug/hard-stack-size` | hard | `qatp:wand` stacks to 64 | static/reasoning |

## Why the tiers matter

The corpus is a **difficulty gradient**, not a flat set, and the gradient is the
result — more than the aggregate score is.

- **Easy** is a control in the other direction. A magenta/black checker is the most
  visually obvious failure Bedrock produces. If it is missed, the run did not look
  at the content at all, and every other number in that run is suspect.
- **Medium** requires cross-referencing a thing's NAME against its APPEARANCE. The
  frame looks perfectly healthy; only "that is not what a marker block should look
  like" catches it.
- **Hard** targets three documented weaknesses, each of which a real pack would ship:
  - **H1** is the render-vs-world-state confusion. The functional lane *passes* it,
    because the block genuinely instantiates. Only vision can catch it, and it has
    to prove an absence.
  - **H2** is pure absence with no artifact whatsoever. It depends on knowing what
    the block was supposed to do.
  - **H3** is invisible to any screenshot and tests whether declared properties are
    verified at all, or only appearance.

An aggregate "found 3 of 6" says little. "Caught 3/3 of the obvious defects and
0/3 of the subtle ones" says exactly where the system stands and what the next
milestone must fix — and it is the harder claim to argue with.

## Reading the results honestly

Three caveats belong in any report built from this corpus:

1. **A miss is not always a failure of judgement.** The agent can fail to *reach*
   or *frame* the content (agency) or misjudge what it saw (judgement). These have
   different fixes. Where the evidence allows, separate them.
2. **Runs on the production service are not independent.** Derived test steps carry
   between runs, so later runs do better. That biases the consistency number
   *optimistically*. It is closed by running with `QA_STATELESS=1`.
3. **This fixture is not a real pack.** Five ids, no scripts, no interactions.
   It measures detection of specific defect classes, not end-to-end performance on
   something like Backpacks++.

## Before trusting any number

Run `main` first and confirm the agent reports **zero** defects against it.

If it reports something, one of two things is true: the fixture is accidentally
broken, or that finding is a false positive. Both matter, and they must be told
apart before any other run is scored — otherwise the false-positive rate is
measuring the fixture rather than the agent.

## Adding a variant

1. `git checkout -b bug/<tier>-<slug> main`
2. Change exactly one thing.
3. Add the entry to `ground-truth.json`, including `whyDetectable`.
4. Confirm the defect cannot prevent the pack loading and cannot gate another
   defect. A masked defect scores as a miss the agent never had a chance at.
