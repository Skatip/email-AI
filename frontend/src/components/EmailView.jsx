import React from "react";

export default function EmailView({ email }) {
  if (!email) {
    return <div className="email-view empty">Select an email</div>;
  }

  return (
    <div className="email-view">
      <h2>{email.subject}</h2>
      <p className="sender">{email.sender}</p>
      <div className="body">{email.body}</div>
    </div>
  );
}