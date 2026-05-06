#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
export PYTHONPATH="$DIR:$PYTHONPATH"
/Users/joelmanuel/.pyenv/versions/3.11.11/bin/python "$DIR/app.py"
