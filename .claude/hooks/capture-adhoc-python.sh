#!/usr/bin/env bash
# Capture ad-hoc Python generation as candidates for extraction into real,
# tested modules. Runs as a PostToolUse hook (Bash + Write/Edit). It never
# blocks or fails the tool — on any problem it exits 0 silently.
#
# Each detected event appends one JSON line to specs/extraction-backlog.jsonl,
# which is reviewed when authoring the next laundry-list spec: each entry is a
# candidate to replace with deterministic code (the way the job-seeker's
# INSERT-generating one-liner became consolidate_module).

payload=$(cat 2>/dev/null) || exit 0
command -v jq >/dev/null 2>&1 || exit 0

tool=$(printf '%s' "$payload" | jq -r '.tool_name // empty' 2>/dev/null) || exit 0
[ -n "$tool" ] || exit 0

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
backlog="$repo_root/specs/extraction-backlog.jsonl"

emit() {
  # $1 = kind, $2 = detail
  mkdir -p "$(dirname "$backlog")" 2>/dev/null || return 0
  jq -nc \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg tool "$tool" \
    --arg kind "$1" \
    --arg detail "$2" \
    --arg cwd "$(pwd)" \
    '{ts:$ts, tool:$tool, kind:$kind, detail:$detail, cwd:$cwd}' \
    >> "$backlog" 2>/dev/null || true
}

case "$tool" in
  Bash)
    cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
    # python -c one-liners, heredocs fed to python, or piping into python.
    if printf '%s' "$cmd" | grep -qE \
      'python[0-9.]*[[:space:]]+-c|python[0-9.]*[[:space:]]*<<|<<[[:space:]]*['"'"'"]?(PY|PYTHON)|\|[[:space:]]*python[0-9.]*([[:space:]]|$)'; then
      emit "bash-adhoc-python" "$(printf '%s' "$cmd" | tr '\n' ' ' | cut -c1-400)"
    fi
    ;;
  Write|Edit|NotebookEdit)
    f=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty' 2>/dev/null) || exit 0
    # A throwaway .py script written under /tmp is a strong extraction signal;
    # .py files inside the repo's package/test trees are real code, not candidates.
    case "$f" in
      *.py)
        case "$f" in
          /tmp/*|*/tmp/*) emit "tmp-python-script" "$f" ;;
        esac
        ;;
    esac
    ;;
esac

exit 0
