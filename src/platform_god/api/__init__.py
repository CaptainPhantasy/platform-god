"""
Platform God API Module.

REST API for agent execution, chain orchestration, and registry queries.
"""

from platform_god.api.app import create_app

__all__ = ["create_app"]

__version__ = "0.1.0"
