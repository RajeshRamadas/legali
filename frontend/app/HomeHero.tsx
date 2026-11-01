"use client";
import { useState } from "react";
import { askAssistant } from "./homeEvents";
import Icon from "./ui/Icon";
export default function HomeHero() {
  const [question, setQuestion] = useState("");
  return (
    <form
      className="hx-hero-ask"
      onSubmit={(e) => {
        e.preventDefault();
        if (question.trim()) askAssistant(question.trim());
      }}
    >
      <Icon name="spark" />
      <input
        aria-label="Ask a property question"
        placeholder="Ask: Is this flat safe to buy?"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        required
        maxLength={1000}
      />
      <button type="submit" aria-label="Ask the legal assistant">
        <Icon name="send" />
      </button>
    </form>
  );
}
