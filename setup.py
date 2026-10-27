#!/usr/bin/env python3
# coding: utf-8

"""
四川旅游问答系统安装脚本
"""

import os
import sys
from setuptools import setup, find_packages

# 获取项目根目录
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# 读取版本号
version = "2.0.0"

# 读取requirements.txt
with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = f.read().splitlines()

# 过滤注释行和空行
requirements = [line for line in requirements if line and not line.startswith(('#', '//'))]

setup(
    name="sichuan_tourism_qa",
    version=version,
    description="四川旅游知识图谱问答系统",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="四川旅游问答团队",
    author_email="example@example.com", # 请替换为实际联系方式
    url="https://github.com/yourusername/SichuanTourismQA", # 请替换为实际GitHub仓库地址
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    package_data={
        "": ["templates/*.html", "dict/*.txt", "*.csv"],
    },
    entry_points={
        "console_scripts": [
            "sichuan-qa=sichuan_qa.cli:main",
        ],
    },
    install_requires=requirements,
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Natural Language :: Chinese (Simplified)",
    ],
)
