"""
Auth utilities.

Currently provides a placeholder for future API-key or JWT validation
middleware.  The AvailityAdapter handles its own OAuth2 token acquisition
internally; this module is reserved for authenticating *incoming* requests.
"""
import logging
from typing import Optional

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)


async def verify_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """
    Optional API-key gate for incoming requests.

    This dependency is a no-op stub – set ``REQUIRE_API_KEY=true`` and
    ``API_KEY=<secret>`` in your environment to activate it (future work).
    """
    # TODO: Read API key from settings and compare with x_api_key.
    pass  # noqa: PIE790  – intentional stub
