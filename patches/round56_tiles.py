#!/usr/bin/env python3
"""Round 56 (26 September), culprits-tiles-more: gfw_copies taken out (Global Forest Watch refuses downloads without an API key). Upload to the culprits-tiles-more repo's patches folder. Safe to run twice."""
import os, shutil, sys
if not os.path.isdir("scripts"):
    sys.exit("Run this from the culprits-tiles-more folder.")
for path in ["scripts/gfw_copies.py"]:
    if os.path.exists(path):
        os.remove(path); print(f"{path}: removed.")
    else:
        print(f"{path}: already gone.")
if os.path.isdir("gfw") and not os.listdir("gfw"):
    shutil.rmtree("gfw")
