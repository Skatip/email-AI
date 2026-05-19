import React from "react";
import EmailCard from "./EmailCard";

export default function InboxList({ emails, onSelect }) {
  return (
    <div className="inbox-list">
      <h3>Inbox</h3>
      {emails.map((email) => (
        <EmailCard key={email.id} email={email} onSelect={onSelect} />
      ))}
    </div>
  );
}