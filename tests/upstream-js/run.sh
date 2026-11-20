#!/usr/bin/env bash
set -euo pipefail

sdk_commit=5e6f990342d72e4440433782795c066703fc8a85
here="$(cd "$(dirname "$0")" && pwd)"
lite="$(cd "$here/../../packages/typescript" && pwd)"
if [[ ! -d "$lite/node_modules/tsx" ]]; then
  echo "Install the Lite test dependencies with npm ci --prefix packages/typescript." >&2
  exit 1
fi

scratch="$(mktemp -d)"
trap 'rm -rf -- "$scratch"' EXIT
git -C "$scratch" init --quiet
git -C "$scratch" fetch --quiet --depth=1 https://github.com/a2aproject/a2a-js.git "$sdk_commit"
git -C "$scratch" checkout --quiet --detach FETCH_HEAD
test "$(git -C "$scratch" rev-parse HEAD)" = "$sdk_commit"

cd "$scratch"
npm ci --ignore-scripts --no-audit --no-fund
npm run build
# Package self-references in the probe resolve to the SDK built at this SHA.
cp "$here/probe.mjs" "$scratch/a2a-lite-canary.mjs"
cd "$lite"
node --import tsx "$scratch/a2a-lite-canary.mjs" "$lite/src/index.ts" "$sdk_commit"
