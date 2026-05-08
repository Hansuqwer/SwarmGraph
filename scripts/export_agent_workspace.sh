#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
out_dir="${1:-$(dirname "$repo_root")}"

mkdir -p "$out_dir"

commit_file="$out_dir/SwarmGraph-COMMIT.txt"
archive_file="$out_dir/SwarmGraph-workspace.zip"
prompt_file="$out_dir/SwarmGraph-agent-access.txt"

git -C "$repo_root" pull --ff-only origin main
git -C "$repo_root" rev-parse HEAD > "$commit_file"
git -C "$repo_root" archive \
  --format=zip \
  --prefix=SwarmGraph/ \
  --output="$archive_file" \
  HEAD

cat > "$prompt_file" <<'EOF'
Blocked: no repository access. Use uploaded pre-cloned workspace instead.

Uploaded files:
- SwarmGraph-workspace.zip
- SwarmGraph-COMMIT.txt

Instructions:
- Extract SwarmGraph-workspace.zip.
- Treat extracted SwarmGraph/ as repository root.
- Read SwarmGraph-COMMIT.txt and report the supplied commit hash.
- Inspect files directly before making claims.
- If Bash/shell is unavailable, provide unified diffs or exact file edits.
- Do not claim tests passed unless you actually ran them.
- If neither this archive nor network clone access is available, stop and output:
  "Blocked: no repository access. Provide a pre-cloned workspace, file bundle, or network clone access."
EOF

printf 'Created:\n'
printf '  %s\n' "$archive_file"
printf '  %s\n' "$commit_file"
printf '  %s\n' "$prompt_file"
