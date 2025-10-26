# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Setup configuration for Smooth Core.

This makes the package pip-installable.
"""
from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

# Core dependencies
install_requires = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.5.3",
    "pydantic-settings>=2.1.0",
    "sqlalchemy>=2.0.25",
    "httpx>=0.26.0",
    "python-multipart>=0.0.6",
    "structlog>=24.1.0",
    "bcrypt>=4.1.2",
    "jinja2>=3.1.2",
]

# Development dependencies
dev_requires = [
    "pytest>=7.4.4",
    "pytest-asyncio>=0.23.3",
    "pytest-cov>=4.1.0",
    "hypothesis>=6.92.2",
    "ruff>=0.1.11",
    "mypy>=1.8.0",
]

# Production database drivers (optional)
postgres_requires = [
    "psycopg2-binary>=2.9.9",
]

mysql_requires = [
    "mysql-connector-python>=8.2.0",
]

setup(
    name="smooth-core",
    version="1.0.0",
    author="Smooth Contributors",
    author_email="",
    description="Vendor-neutral tool data synchronization system",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/sliptonic/smooth-core",
    project_urls={
        "Bug Tracker": "https://github.com/sliptonic/smooth-core/issues",
        "Documentation": "https://github.com/sliptonic/smooth-core/blob/main/README.md",
        "Source Code": "https://github.com/sliptonic/smooth-core",
    },
    packages=find_packages(exclude=["tests", "tests.*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Manufacturing",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Database",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Framework :: FastAPI",
    ],
    python_requires=">=3.11",
    install_requires=install_requires,
    extras_require={
        "dev": dev_requires,
        "postgres": postgres_requires,
        "mysql": mysql_requires,
        "all": dev_requires + postgres_requires + mysql_requires,
    },
    entry_points={
        "console_scripts": [
            "smooth-server=smooth.main:cli",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
