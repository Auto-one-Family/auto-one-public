"""Setup script for god_kaiser_server - enables pip install -e ."""
from setuptools import setup, find_packages

setup(
    name="god_kaiser_server",
    version="1.0.0",
    package_dir={"god_kaiser_server": "src"},
    packages=["god_kaiser_server"] + [f"god_kaiser_server.{pkg}" for pkg in find_packages(where="src")],
    python_requires=">=3.11",
    install_requires=[
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "sqlalchemy>=2.0.25",
        "alembic>=1.13.1",
        "pydantic[email]>=2.5.3",
        "pydantic-settings>=2.1.0",
        "paho-mqtt>=1.6.1",
        "aiomqtt>=2.0.1",
        "python-jose[cryptography]>=3.3.0",
        "passlib[bcrypt]>=1.7.4",
        "python-dotenv>=1.0.0",
        "python-dateutil>=2.8.2",
        "pytz>=2024.1",
        "httpx>=0.26.0",
        "aiohttp>=3.9.3",
        "websockets>=12.0",
        "prometheus-client>=0.19.0",
        "python-multipart>=0.0.6",
        "aiosqlite>=0.20.0",
    ],
)

