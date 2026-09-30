"""pytest 配置：确保 backend 包可被导入。"""
import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
repo_dir = os.path.dirname(backend_dir)
sys.path.insert(0, backend_dir)
sys.path.insert(0, os.path.join(repo_dir, "robot_contracts"))

