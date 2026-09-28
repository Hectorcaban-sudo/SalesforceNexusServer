"""Outbound integration fan-out."""
from .integration_dispatch import dispatch_integrations

__all__ = ["dispatch_integrations"]
