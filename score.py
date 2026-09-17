#!/usr/bin/env python3
"""Score qa-bench results against the corpus ground truth.

Reads the raw job JSON each run saved and answers Milestone 1's question:
how many known defects were found, how many findings were not real, how long
it took, and whether repeated runs agree.

Finding extraction is deliberately SCHEMA-TOLERANT. The agent stores a
lane-dependent result blob (visual bugs, non-visual findings, vision reports),
so instead of hardcoding a path this deep-walks the result for objects that
look like findings. A scorer that silently finds nothing because a key moved
would report a perfect false-positive rate and a catastrophic miss rate — both
wrong, and both plausible-looking.
"""
import json, os, sys
from collections import defaultdict

TERMINAL = {"pass", "fail", "error"}


def walk_findings(node, out, depth=0):
    """Collect finding-shaped dicts anywhere in the result blob."""
    if depth > 12:
        return
    if isinstance(node, dict):
        # A finding has a title and a severity; content_id is optional because
        # findings that name no id are real (a broken recipe, a bad tooltip).
        if "title" in node and "severity" in node and isinstance(node.get("title"), str):
            out.append({
                "content_id": node.get("content_id") or node.get("contentId"),
                "title": node.get("title", ""),
                "severity": node.get("severity", ""),
                "category": node.get("category", "visual" if "shots" in node else ""),
            })
            return
        for v in node.values():
            walk_findings(v, out, depth + 1)
    elif isinstance(node, list):
        for v in node:
            walk_findings(v, out, depth + 1)


def load_runs(outdir, ref):
    slug = ref.replace("/", "-")
    d = os.path.join(outdir, slug)
    runs = []
    if not os.path.isdir(d):
        return runs
    for f in sorted(os.listdir(d)):
        if not f.startswith("run-") or not f.endswith(".json"):
            continue
        with open(os.path.join(d, f)) as fh:
            try:
                job = json.load(fh)
            except json.JSONDecodeError:
                continue
        findings = []
        walk_findings(job.get("result", job), findings)
        runs.append({
            "file": f,
            "status": job.get("status", "unknown"),
            "wall": (job.get("_bench") or {}).get("wallSeconds"),
            "findings": findings,
            "ids": {f["content_id"] for f in findings if f.get("content_id")},
        })
    return runs


def main(gt_path, outdir):
    gt = json.load(open(gt_path))
    variants = gt["variants"]

    # The control run defines which findings are "background": anything the agent
    # reports against the undamaged pack is either a false positive or a fixture
    # bug. Either way it must not be counted against the broken variants.
    control = next((v for v in variants if v["tier"] == "control"), None)
    control_ids, control_titles = set(), set()
    control_runs = load_runs(outdir, control["ref"]) if control else []
    for r in control_runs:
        control_ids |= r["ids"]
        control_titles |= {f["title"] for f in r["findings"] if not f.get("content_id")}

    report, summary = [], {"variants": [], "control": {}}
    report.append("# QA Agent — Milestone 1 baseline\n")
    report.append(f"Corpus `{gt.get('corpus')}` · ground truth: {len(variants)} variants\n")

    if control:
        n = len(control_runs)
        report.append("## Control (undamaged pack)\n")
        if not control_runs:
            report.append("> **Not yet run.** Run the control first — until it is clean, "
                          "no false-positive number below can be trusted.\n")
        else:
            per = [len(r["findings"]) for r in control_runs]
            report.append(f"`{control['ref']}` — {n} run(s), findings per run: "
                          f"{' / '.join(map(str, per)) or '—'}\n")
            if any(per):
                report.append(
                    "> Findings on a pack with no known defect. Each is **either a false "
                    "positive or a fixture bug**, and they must be told apart before the "
                    "rates below mean anything. They are excluded as background.\n")
                for i in sorted(control_ids):
                    report.append(f"> - `{i}`\n")
            else:
                report.append("> Clean — no findings. Good baseline.\n")
        summary["control"] = {"ref": control["ref"], "runs": n,
                              "findingsPerRun": [len(r["findings"]) for r in control_runs],
                              "backgroundIds": sorted(control_ids)}

    report.append("\n## Per variant\n")
    report.append("| Variant | Tier | Runs | Detected | False positives | Wall (s) |")
    report.append("|---|---|---|---|---|---|")

    detail, tiers = [], defaultdict(lambda: {"hit": 0, "total": 0})

    for v in variants:
        if v["tier"] == "control":
            continue
        runs = load_runs(outdir, v["ref"])
        expected = {d["contentId"]: d for d in v["defects"] if d.get("contentId")}
        if not runs:
            report.append(f"| `{v['ref']}` | {v['tier']} | 0 | _not run_ | — | — |")
            continue

        det, fps, walls = [], [], []
        per_defect = defaultdict(list)
        for r in runs:
            hit = {cid for cid in expected if cid in r["ids"]}
            det.append(len(hit))
            # A false positive names something that is not the injected defect and
            # was not already reported against the undamaged control.
            fp = (r["ids"] - set(expected) - control_ids)
            fp |= {f["title"] for f in r["findings"]
                   if not f.get("content_id") and f["title"] not in control_titles}
            fps.append(len(fp))
            if r["wall"] is not None:
                walls.append(r["wall"])
            for cid in expected:
                per_defect[cid].append(cid in hit)

        report.append(
            f"| `{v['ref']}` | {v['tier']} | {len(runs)} | "
            f"{'/'.join(str(d) for d in det)} of {len(expected)} | "
            f"{'/'.join(str(f) for f in fps)} | "
            f"{'/'.join(str(w) for w in walls) if walls else '—'} |")

        detail.append(f"\n### `{v['ref']}` — {v['tier']}\n")
        for cid, d in expected.items():
            hits = per_defect[cid]
            mark = "always" if all(hits) else ("never" if not any(hits) else "**flaky**")
            detail.append(f"- `{cid}` — {sum(hits)}/{len(hits)} runs — {mark}  ")
            detail.append(f"  {d['symptom']}")
            tiers[v["tier"]]["hit"] += sum(hits)
            tiers[v["tier"]]["total"] += len(hits)

        summary["variants"].append({
            "ref": v["ref"], "tier": v["tier"], "runs": len(runs),
            "injected": len(expected), "detectedPerRun": det,
            "falsePositivesPerRun": fps, "wallSeconds": walls,
            "perDefect": {cid: per_defect[cid] for cid in expected},
        })

    report.append("\n## Detection by tier\n")
    report.append("| Tier | Caught | Rate |")
    report.append("|---|---|---|")
    for t in ("easy", "medium", "hard"):
        if tiers[t]["total"]:
            h, n = tiers[t]["hit"], tiers[t]["total"]
            report.append(f"| {t} | {h}/{n} | {100*h//n}% |")
    summary["byTier"] = {t: dict(tiers[t]) for t in tiers}

    report += detail
    report.append("\n## Reading this\n")
    report.append("- **Detected** is per run, in order. `2/2/1` means the third run "
                  "found one fewer than the first two — that is the consistency signal.")
    report.append("- A **flaky** defect matters more than a missed one: a check that "
                  "passes two runs in three cannot be trusted on either outcome.")
    report.append("- Rates are over a 5-id fixture, not a shipping pack. They measure "
                  "detection of specific defect classes, not end-to-end performance.")
    report.append("- Unless the agent ran with `QA_STATELESS=1`, derived test steps "
                  "carry between runs, so later runs are helped by earlier ones and the "
                  "consistency figure is **optimistic**.")

    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(outdir, "baseline.md"), "w").write("\n".join(report) + "\n")
    json.dump(summary, open(os.path.join(outdir, "baseline.json"), "w"), indent=2)
    print("\n".join(report))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: score.py <ground-truth.json> <results-dir>")
    main(sys.argv[1], sys.argv[2])
