#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

cd frontend
npm run build
cd ..

rm -rf api/static
cp -R frontend/dist api/static
