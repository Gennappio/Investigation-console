"""Python client for the platform's agent-facing interface.

The client speaks the documented CLI JSON contracts (``docs/protocols/cli.md``)
and holds no business logic of its own: it is the reference implementation of
those contracts, not a second copy of the platform.
"""

from lab_api_client.client import LabClient, LabCommandError

__all__ = ["LabClient", "LabCommandError"]
