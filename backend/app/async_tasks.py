from app.celery_app import celery_app
from app.ai_workflows import (
    analyze_email_workflow,
    reply_generate_workflow,
    multi_reply_workflow,
    thread_summary_workflow,
    attachment_analyze_workflow,
    compose_notes_workflow,
    check_due_followups_workflow,
)


@celery_app.task(name="app.tasks.analyze_email")
def analyze_email_task(payload):
    return analyze_email_workflow(payload or {})


@celery_app.task(name="app.tasks.generate_reply")
def generate_reply_task(payload):
    return reply_generate_workflow(payload or {})


@celery_app.task(name="app.tasks.generate_multi_reply")
def generate_multi_reply_task(payload):
    return multi_reply_workflow(payload or {})


@celery_app.task(name="app.tasks.thread_summary")
def thread_summary_task(payload):
    return thread_summary_workflow(payload or {})


@celery_app.task(name="app.tasks.attachment_analyze")
def attachment_analyze_task(payload):
    return attachment_analyze_workflow(payload or {})


@celery_app.task(name="app.tasks.compose_notes")
def compose_notes_task(payload):
    return compose_notes_workflow(payload or {})


@celery_app.task(name="app.tasks.check_due_followups")
def check_due_followups_task(payload=None):
    return check_due_followups_workflow(payload or {})
