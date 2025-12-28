"""
NetStacks Core - Shared library for NetStacks microservices
"""
from setuptools import setup, find_packages

setup(
    name="netstacks-core",
    version="1.0.0",
    description="Shared library for NetStacks microservices",
    author="NetStacks Team",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "sqlalchemy>=2.0.0",
        "psycopg2-binary>=2.9.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "cryptography>=41.0.0",
        "python-jose[cryptography]>=3.3.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
        ],
    },
)
