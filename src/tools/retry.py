"""
AegisOps — Retry Decorator

Provides exponential backoff retry logic for GCP tool calls.
Catches transient errors (network timeouts, 5xx responses)
and retries with increasing delays.

Usage:
    @with_retry(max_attempts=3)
    def my_gcp_tool(...):
        ...
"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable


# Exceptions that are considered transient and worth retrying
TRANSIENT_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)

# Try to include Google API exceptions if available
try:
    from google.api_core.exceptions import (
        ServiceUnavailable,
        InternalServerError,
        GatewayTimeout,
        TooManyRequests,
    )
    TRANSIENT_EXCEPTIONS = (
        *TRANSIENT_EXCEPTIONS,
        ServiceUnavailable,
        InternalServerError,
        GatewayTimeout,
        TooManyRequests,
    )
except ImportError:
    pass


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
) -> Callable:
    """
    Decorator that adds exponential backoff retry logic.

    Args:
        max_attempts: Maximum number of attempts (including the first).
        base_delay: Initial delay in seconds before first retry.
        max_delay: Cap on delay between retries.
        backoff_factor: Multiply delay by this factor each retry.

    Returns:
        Decorated function with retry logic.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            delay = base_delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except TRANSIENT_EXCEPTIONS as e:
                    last_exception = e
                    if attempt == max_attempts:
                        print(
                            f"  [ERROR] [{func.__name__}] All {max_attempts} attempts "
                            f"exhausted. Last error: {e}"
                        )
                        return {
                            "success": False,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "attempts": attempt,
                            "message": (
                                f"Tool '{func.__name__}' failed after "
                                f"{max_attempts} retries: {e}"
                            ),
                        }

                    print(
                        f"  [RETRY] [{func.__name__}] Attempt {attempt}/{max_attempts} "
                        f"failed: {e}. Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)

                except Exception as e:
                    # Non-transient errors are NOT retried
                    print(f"  [ERROR] [{func.__name__}] Non-transient error: {e}")
                    return {
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "attempts": attempt,
                        "message": f"Tool '{func.__name__}' failed (non-retryable): {e}",
                    }

            # Should not reach here, but just in case
            return {
                "success": False,
                "error": str(last_exception),
                "message": f"Tool '{func.__name__}' failed unexpectedly.",
            }

        return wrapper
    return decorator
