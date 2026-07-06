import os
from typing import Any, Callable, Dict, Optional


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def async_enabled() -> bool:
    return _truthy(os.getenv("AI_ASYNC_ENABLED", "false"))


def fallback_enabled() -> bool:
    return _truthy(os.getenv("AI_ASYNC_FALLBACK_ON_ERROR", "true"))


def default_timeout() -> int:
    try:
        return int(os.getenv("AI_ASYNC_WAIT_TIMEOUT", "90"))
    except Exception:
        return 90


def run_ai_workflow_sync(
    task_name: str,
    payload: Dict[str, Any],
    local_fallback: Callable[[Dict[str, Any]], Any],
    timeout: Optional[int] = None,
) -> Any:
    """
    Keeps existing API response shapes intact.

    - If AI_ASYNC_ENABLED=false: runs local function exactly like before.
    - If AI_ASYNC_ENABLED=true: sends heavy work to Celery/Redis and waits for result.
      FastAPI no longer performs OCR/LLM/reply/thread work inside its process.
    - If Redis/Celery is unavailable and fallback is enabled: runs local function so UI does not break.
    """
    if not async_enabled():
        return local_fallback(payload)

    try:
        from app.celery_app import celery_app
        result = celery_app.send_task(task_name, args=[payload])
        return result.get(timeout=timeout or default_timeout(), propagate=True)
    except Exception:
        if fallback_enabled():
            return local_fallback(payload)
        raise


def submit_ai_workflow(task_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optional future-proof endpoint support. Does not affect current UI.
    Useful later when frontend wants true non-blocking polling by task_id.
    """
    from app.celery_app import celery_app
    result = celery_app.send_task(task_name, args=[payload])
    return {"task_id": result.id, "status": "queued"}


def get_task_status(task_id: str) -> Dict[str, Any]:
    from app.celery_app import celery_app
    result = celery_app.AsyncResult(task_id)
    response: Dict[str, Any] = {
        "task_id": task_id,
        "status": result.status,
        "ready": result.ready(),
    }
    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)
    return response
