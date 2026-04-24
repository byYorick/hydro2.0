# GPT-5.1 Codex Max Prompting Guide

This quick-reference summarizes the OpenAI cookbook guidance for GPT-5.1 Codex Max and adapts it for this project.

## Principles for effective prompts
- **State the job clearly.** Declare the user goal, constraints, and what success looks like (expected fields, format, tone).
- **Ground the model.** Share domain context, existing conventions, and any files or examples to reuse instead of inventing new patterns.
- **Prefer instructions over hints.** Use imperative language ("Return JSON with these keys", "Do not edit migrations") and avoid vague suggestions.
- **Constrain outputs.** Specify schemas, delimiters, code fences, and whether reasoning should be hidden or shown.
- **Show exemplars.** Provide one or two realistic input/output pairs, including edge cases, so the model can mirror the style.
- **Minimize ambiguity.** Highlight forbidden behaviors (e.g., avoid dependencies, keep functions pure) and call out trade-offs explicitly.
- **Iterate in layers.** Start with a concise brief, then add targeted refinements (tests, error handling, performance) instead of rewriting the whole prompt.

## Tool and code-generation tips
- Describe available tools or commands, including parameters, required safety checks, and what to return after tool calls.
- When generating code, request filenames, function signatures, and assumptions (env vars, secrets, service ports) to reduce back-and-forth.
- If branch or PR creation fails, surface the exact tool error and propose a workaround (manual branch creation, permission check).
- Ask for unit tests and validation cases up front; prefer idempotent operations and clear rollback notes for migrations or data scripts.
- For long responses, ask for structured sections (Summary, Changes, Tests) and keep noisy logs collapsed or omitted.

### Troubleshooting branch/PR creation errors
- Quote the tool error verbatim (no paraphrasing) and note which step failed.
- Check permissions: ensure push/branch creation is allowed and that the default branch is not protected.
- Suggest a workaround: manually create the branch, specify origin/upstream explicitly, or retry with the correct branch name.
- If the issue persists, capture repro info—tool version (if shown), exact command/params, timestamp, and task context—to simplify debugging.

## Quality controls
- Encourage the model to verify steps: "List risks before coding", "Re-read the schema and confirm types", or "Run through acceptance criteria".
- Require explicit handling of edge cases, error states, and authorization boundaries.
- Tell the model to flag missing inputs instead of fabricating values.
- Invite self-checks: "Validate output against the schema and report any deviations".

## Handy prompt template
Use this skeleton as a starting point and adapt details per task:

```
You are GPT-5.1 Codex Max helping with <project/module>.
Goal: <what should be built or fixed>.
Context: <key domain rules, files, APIs, dependencies>.
Constraints: <forbidden actions, performance/UX/security requirements>.
Output: <exact format, files, sections, schemas>.
Examples: <optional I/O pairs or snippets to mirror tone/style>.
Checks: <tests to add/run, validations, risks to call out>.
```

## Reference
- Source: OpenAI Cookbook — GPT-5.1 Codex Max prompting guide (https://cookbook.openai.com/examples/gpt-5/gpt-5-1-codex-max_prompting_guide).
