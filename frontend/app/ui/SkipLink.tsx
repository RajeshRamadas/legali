"use client";

export default function SkipLink() {
  return <a className="hx-skip-link" href="#main-content" onClick={(event) => {
    const content = document.getElementById("main-content");
    if (content) {
      event.preventDefault();
      content.focus();
      content.scrollIntoView({ block: "start", behavior: "instant" });
    }
  }}>Skip to main content</a>;
}
