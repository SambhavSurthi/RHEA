"""Shared FastAPI dependencies."""

from fastapi import Request

from rhea.core.bootstrap import Services


def get_services(request: Request) -> Services:
    """Return the service container created by the application factory."""
    return request.app.state.services
