# qa-bench — harness for the qa-testpack corpus

Deliberately an ORPHAN branch: `main` and every `bug/*` branch stay pure pack
content, so each variant differs from `main` by exactly one file. The QA agent
never builds this branch.

## Install on the VPS

    mkdir -p ~/bin
    curl -sS -o ~/bin/qa-bench https://raw.githubusercontent.com/RAIXOCZ/qa-testpack/tools/qa-bench
    curl -sS -o ~/bin/score.py https://raw.githubusercontent.com/RAIXOCZ/qa-testpack/tools/score.py
    chmod +x ~/bin/qa-bench ~/bin/score.py

Needs `curl`, `jq`, `python3`, and the token at `~/.config/qa-token`.
`score.py` must sit next to `qa-bench` — the runner resolves it by dirname.

## Use

    qa-bench run -n 1 -v main    # control first: it MUST come back clean
    qa-bench all                 # all variants x3, then score
    qa-bench report              # re-score what is already on disk
