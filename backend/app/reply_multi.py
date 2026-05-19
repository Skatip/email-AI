from typing import Dict, Any, List

from app.reply_agent import draft_reply


def generate_multi(email: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    replies: List[str] = []

    for _ in range(3):
        res = draft_reply(email, analysis)
        reply = (res or {}).get("reply", "").strip()
        if reply and reply not in replies:
            replies.append(reply)

    return {
        "options": replies,
        "count": len(replies),
    }