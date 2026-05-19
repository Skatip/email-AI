import React from "react";

export default function AIPanel({ email }) {
  if (!email) {
    return <div className="ai-panel empty">AI Analysis</div>;
  }

  return (
    <div className="ai-panel">
      <h3>AI Analysis</h3>

      <div className="ai-item">
        <span>Priority:</span> {email.priority}
      </div>

      <div className="ai-item">
        <span>Risk:</span> {email.risk}
      </div>

      <div className="ai-item">
        <span>Band:</span> {email.sender_band}
      </div>

      <div className="ai-item">
        <span>Intent:</span> {email.intent}
      </div>

      <div className="ai-item">
        <span>Emotion:</span> {email.emotion}
      </div>

      <div className="ai-summary">
        <h4>Summary</h4>
        <p>{email.summary}</p>
      </div>

      <div className="ai-reply">
        <h4>Suggested Reply</h4>
        <textarea value={email.suggested_reply} readOnly />
      </div>
    </div>
  );
}