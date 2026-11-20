#!/usr/bin/env python3
"""A stand-in model command for trying the whole flow without a model: copies the given file to the report path.

  python3 fake_model.py CANNED_REPORT        (RB_REPORT_PATH is set by remote_run.py)
"""
import os
import shutil
import sys

target = os.environ["RB_REPORT_PATH"]
os.makedirs(os.path.dirname(target), exist_ok=True)
shutil.copy(sys.argv[1], target)
print('{"status": "SUCCESS", "usage": {"input_tokens": 1000, "cache_read_tokens": 400, "output_tokens": 200}}')
