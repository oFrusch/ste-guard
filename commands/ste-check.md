---
description: Lint a file or the last reply against the active STE profile
---

Run the STE checker against the target the user named in `$ARGUMENTS`.

- When `$ARGUMENTS` holds a file path, pass that path to `"${CLAUDE_PLUGIN_ROOT}"/hooks/ste-check`.
- When `$ARGUMENTS` is empty, check your own previous reply. Pipe it to the checker on stdin.

Report the violations verbatim. Then offer a corrected version of the text.
