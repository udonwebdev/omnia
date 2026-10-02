import functools
import inspect
from policy_engine import policy_engine
from audit_logger import audit_logger

def guard_action(func):
    """Decorator ensuring all tool executions pass through the policy engine and audit logger."""
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        # Extract function arguments as dictionary
        sig = inspect.signature(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        params = bound.arguments

        tool_name = func.__name__
        allowed, message = policy_engine.verify_action(tool_name, params)

        if not allowed:
            audit_logger.log_event(tool_name, params, allowed=False, outcome=message)
            return f"[POLICY REJECTION] Action blocked by Omnia Governance: {message}"

        try:
            if inspect.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            audit_logger.log_event(tool_name, params, allowed=True, outcome="Success")
            return result
        except Exception as e:
            audit_logger.log_event(tool_name, params, allowed=True, outcome=f"Failed: {str(e)}")
            raise e

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        sig = inspect.signature(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        params = bound.arguments

        tool_name = func.__name__
        allowed, message = policy_engine.verify_action(tool_name, params)

        if not allowed:
            audit_logger.log_event(tool_name, params, allowed=False, outcome=message)
            return f"[POLICY REJECTION] Action blocked by Omnia Governance: {message}"

        try:
            result = func(*args, **kwargs)
            audit_logger.log_event(tool_name, params, allowed=True, outcome="Success")
            return result
        except Exception as e:
            audit_logger.log_event(tool_name, params, allowed=True, outcome=f"Failed: {str(e)}")
            raise e

    return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
