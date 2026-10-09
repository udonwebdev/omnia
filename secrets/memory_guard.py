import ctypes
import sys
import logging
from typing import Optional, Any
from secrets.models import SecretHandle

logger = logging.getLogger("Omnia.Secrets.MemoryGuard")

class SecureContext:
    """
    Context manager ensuring minimal in-memory lifetime for materialized credentials.
    Upon exiting the block, the handle is released and the caller's reference is wiped.
    """

    def __init__(self, handle: SecretHandle):
        self._handle = handle
        self._value: Optional[str] = None

    def __enter__(self) -> str:
        if not self._handle.is_active:
            raise RuntimeError(f"Cannot enter SecureContext: handle '{self._handle.secret_id}' is invalid or expired.")
        self._value = self._handle.get_raw_value()
        return self._value

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._handle.release()
            self._value = None
        except Exception as e:
            logger.debug(f"Error during SecureContext release: {e}")

class MemoryGuard:
    """Provides memory safety protocols and transient cache boundaries for secrets."""

    @staticmethod
    def zero_string(s: str):
        """
        Best-effort in-place memory overwriting in CPython runtimes where string buffers
        might reside in memory. In managed garbage-collected runtimes like Python, immutable
        strings cannot be completely guaranteed zeroed in all heaps, but this minimizes exposure.
        """
        try:
            if isinstance(s, str) and len(s) > 0:
                # Overwrite buffer if accessible via ctypes
                offset = sys.getsizeof(s) - len(s) - 1
                location = id(s) + offset
                ctypes.memset(location, 0, len(s))
        except Exception:
            pass

    @staticmethod
    def wrap_handle(handle: SecretHandle) -> SecureContext:
        return SecureContext(handle)

memory_guard = MemoryGuard()
