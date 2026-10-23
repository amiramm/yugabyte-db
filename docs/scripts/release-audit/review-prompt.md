# Feature page review prompt

Use this prompt for one agent per area, such as Connection Manager, CDC or observability. Fill in the angle-bracket placeholders, then run the agents in parallel.

```text
You are reviewing YugabyteDB docs for the <series> release series against the source code.
Goal: find factual inaccuracies (wrong flag/GUC/function/view/column names, defaults,
behaviors, permissions, limitations, syntax) and important missing coverage.
Do NOT edit any repo files. Read-only review.

- Docs for <series> are in docs/content/stable/.
- The release being documented is tag `<tag>`. Read code AT THAT TAG with
  `git show <tag>:<path>` and `git grep -n <pattern> <tag> -- src/`. The working
  tree is master, which can contain code that the release doesn't have.
- Ground truth for flag defaults: <path>/tserver.xml and <path>/master.xml, downloaded from
  https://downloads.yugabyte.com/releases/<version>/yugabyte-<version>-b<build>-{tserver,master}_flags.xml
  (hidden flags are omitted; AutoFlags show initial/target).
- PG GUCs: src/postgres/src/backend/utils/misc/guc.c. Catalog, views and functions:
  src/postgres/src/include/catalog/*.dat and the yb_*.sql files.
- Release notes: docs/content/stable/releases/ybdb-releases/<series>.md

Your scope:
<list the pages and the features or flags to check>

For each claim, find the code that implements it. Report ONLY verified findings, each as:
doc file:line, what the doc says, what the code says (path:line at the tag), and severity
(wrong / misleading / missing). List suspicions separately, labeled UNVERIFIED.
Keep the report under about 700 words.
```

Before you file a finding, spot-check it yourself. Agent reports can be wrong in the same confident tone as right ones.
