#!/bin/zsh
set -eu
cd "${0:A:h}"
umask 077
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  print -u2 'Set OPENAI_API_KEY in this shell; never put it in Git or frontend code.'
  exit 1
fi
[[ -x .venv/bin/python ]] || { python3 -m venv .venv; .venv/bin/pip install -r requirements.txt; }
[[ -d node_modules ]] || npm ci --no-audit --no-fund
npm run build
print 'Self Podcast: http://127.0.0.1:8765 (leave this terminal open)'
exec .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8765 --no-access-log
