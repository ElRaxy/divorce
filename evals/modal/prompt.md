---
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Write, Edit, Glob, Grep, Skill, Bash]
runs: 3
---

Write index.html in the current working directory for a small document manager. Show a page title, one saved document, and a Delete action. Activating Delete should open a confirmation modal with Cancel and Delete choices. Cancel keeps the document; confirming removes it and shows a short confirmation. Include working keyboard operation, Escape to cancel, and sensible focus when the modal opens and closes.

Create a complete, standalone HTML document in English with a doctype, language, character encoding, and title. Use only inline CSS and any JavaScript needed for the behavior. Do not use frameworks, CDNs, remote images, external fonts, or other external resources. Do not open a browser. The deliverable is the file, not a code block in the reply.
