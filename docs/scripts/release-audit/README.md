# Release docs audit

How to check the docs for a release series against the code that shipped. The first run (v2026.1 against 2026.1.2.0-b137) found about 70 inaccuracies.

Two parts:

1. **Flag reference audit**: a script compares the yb-tserver and yb-master flag pages with the flag files published for the release. It takes about a minute.
2. **Feature page review**: people or agents check each feature page against the code at the release tag. Plan for a few hours.

## Ground truth

- **Code**: the release tag, such as `2026.1.2.0-b137`, never `master`. Docs for the stable series are edited on master, so master can already contain code (and docs) that the release doesn't have.
- **Flag defaults**: the flag files published for each build:
  `https://downloads.yugabyte.com/releases/<version>/yugabyte-<version>-b<build>-{tserver,master}_flags.xml`
  These hold each process's real default, including master overrides that differ from the default in source. Examples: on yb-master, `log_min_seconds_to_retain` is 7200 and `durable_wal_write` is true. AutoFlags show `initial` and `target` values. Hidden flags are left out.

## Steps

### 1. Sync and identify the release

```sh
git fetch upstream --tags
git switch --detach upstream/master
# The release and build the stable docs describe:
python3 -c "import json;[print(v['series'],v.get('alias',''),v['appVersion']) for v in json.load(open('docs/data/currentVersions.json'))['dbVersions']]"
git tag -l '2026.1.2.0-b137'   # confirm the tag exists
```

### 2. Run the flag audit

```sh
python3 docs/scripts/release-audit/audit_flag_docs.py \
  --series stable --prev 2025.2.7.0-b107 -o flag-report.md
```

- `--release` defaults to the `appVersion` of `--series` in `docs/data/currentVersions.json`.
- `--prev` is the previous release to diff against. With it, the report also lists new flags that no page mentions, and removed flags that pages still mention.

The report has these sections:

| Section | What it means |
| --- | --- |
| Default mismatches | The documented default differs from the binary. |
| Documented on the wrong process page | The flag exists only on the other process (yb-tserver vs yb-master). |
| Documented but not in the binary | The flag doesn't exist, was renamed, or is hidden. |
| Deprecated in binary, not marked in doc | The binary tags the flag deprecated, but the page doesn't say so. |
| New flags no page mentions | Candidates for missing coverage. |
| Removed flags still in docs | Stale content, or content documented ahead of the release. |

Expect noise. These rows don't need fixing:

- Prose defaults, such as "Same as `--fs_data_dirs`".
- Computed defaults, such as bind addresses and webserver ports.
- Sentinels, such as -1000 ("use the recommended value").
- Hidden flags such as `disable_deadlock_detection` show up as "not in binary". Check the source to confirm the flag still exists before you remove its docs.

### 3. Verify each candidate in code

```sh
T=2026.1.2.0-b137
git grep -n 'DEFINE.*<flag_name>' $T -- src/yb
git show "${T}:src/yb/<path>"       # in zsh, write ${T}: so :s isn't parsed as a modifier
```

### 4. Check for content that hasn't shipped

For each flag, GUC, function or metric a stable page names:

- **Absent at the tag**: `git grep -c <name> $T -- src` returns nothing. Find the commit that added it and the release branches that contain it:
  ```sh
  git log --format='%h %ad %s' --date=short -S <name> upstream/master -- src | tail -1
  git branch -r --contains <sha> | grep 2026
  ```
- **On the release branch but not in the release**: either label the content with the release that ships it ("v2026.1.3 and later") or hold the doc change until that release.

### 5. Review feature pages

For each row under **Highlights** and **New features** in the series' release notes, review the linked page against code at the tag. Check:

- Flag and GUC names, defaults, and whether a change needs a restart (runtime vs non-runtime, `PGC_*` context).
- Required privileges.
- Syntax.
- Documented limitations, compared with the "not supported" errors in code.
- Version availability.

With Claude Code, run one agent per area in parallel. Use the prompt in [review-prompt.md](review-prompt.md).

### 6. Check the release notes

For a changelog line you doubt, find its commit and the release that first contains it:

```sh
git log --oneline upstream/2026.1 --grep='#31149'
for t in 2026.1.0.0-b118 2026.1.1.0-b91 2026.1.2.0-b137; do
  git merge-base --is-ancestor <sha> $t && echo "in $t"
done
```

Then read the commit message and diff. Check that the note describes what the change does, not just its title.

### 7. File and record

- File the findings under a DOC epic with component `documentation` and a label such as `doc-2026.1`.
- Group fixes by page, so that each fix PR stays small.
- Save anything you learn about how the code works to the shared Meko datapack `adlc/proj/yugabyte-db/yugabytedb-docs`. The next audit starts from there.
