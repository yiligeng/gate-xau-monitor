#!/bin/zsh

set -u

PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR" || exit 1

export PYTHONPATH="$PROJECT_DIR/src"
python3 -m xau_monitor --web --quote-interval 0.25 --analysis-interval 5
