#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
export PYTHONPATH="$DIR:$DIR/browser-harness/src:$PYTHONPATH"
/Users/joelmanuel/.pyenv/versions/3.11.11/bin/python3.11 "$DIR/app.py"
