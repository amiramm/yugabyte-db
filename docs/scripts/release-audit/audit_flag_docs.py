#!/usr/bin/env python3
"""Audit the yb-tserver / yb-master flag reference pages against a released build.

Compares every `##### --flag` entry in
docs/content/<series>/reference/configuration/yb-{tserver,master}.md with the
flag dump published for the release (the same files the "All flags" pages use):
  https://downloads.yugabyte.com/releases/<version>/yugabyte-<version>-b<build>-<process>_flags.xml

Those XML files hold the shipped, process-specific defaults (master overrides
included). AutoFlags show initial/target values; hidden flags are omitted.

Usage (from the repo root):
  python3 audit_flag_docs.py                     # stable series, version from docs/data/currentVersions.json
  python3 audit_flag_docs.py --series stable --prev 2025.2.7.0-b107
  python3 audit_flag_docs.py --release 2026.1.2.0-b137 --prev 2025.2.7.0-b107 -o report.md

Output is a Markdown report. Expect some noise: defaults written as prose
("Same as --fs_data_dirs"), computed defaults (webserver ports, bind
addresses), and sentinel values such as -1000. Triage before filing.
"""
import argparse, json, os, re, sys, urllib.request
import xml.etree.ElementTree as ET

URL = "https://downloads.yugabyte.com/releases/{v}/yugabyte-{v}-b{b}-{p}_flags.xml"
PROCS = {"tserver": "yb-tserver.md", "master": "yb-master.md"}


def split_release(rel):
    m = re.fullmatch(r"(\d+\.\d+\.\d+\.\d+)-b(\d+)", rel)
    if not m:
        sys.exit(f"release must look like 2026.1.2.0-b137, got {rel!r}")
    return m.group(1), m.group(2)


def release_from_docs(series):
    data = json.load(open("docs/data/currentVersions.json"))
    for v in data["dbVersions"]:
        if (v.get("alias") or v["series"]) == series:
            return v["appVersion"]
    sys.exit(f"series {series!r} not found in docs/data/currentVersions.json")


def fetch(rel, proc, cache):
    v, b = split_release(rel)
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, f"{v}-b{b}-{proc}.xml")
    if not os.path.exists(path):
        # The download host rejects urllib's default User-Agent.
        req = urllib.request.Request(URL.format(v=v, b=b, p=proc), headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req) as r, open(path, "wb") as f:
            f.write(r.read())
    flags = {}
    for f in ET.parse(path).getroot().findall("flag"):
        flags[f.findtext("name")] = {
            "default": f.findtext("default"),
            "initial": f.findtext("initial"),
            "target": f.findtext("target"),
            "tags": (f.findtext("tags") or "").split(","),
            "meaning": f.findtext("meaning") or "",
        }
    return flags


def norm(v):
    v = (v or "").strip().strip("`").strip().replace('"', "").replace("'", "")
    v = re.sub(r"\s+", " ", v).rstrip(".")
    # Evaluate simple arithmetic such as `5 * 60 * 1000` or `4 * 3600`.
    if re.fullmatch(r"[\d\s*+\-/().]+", v) and re.search(r"\d", v):
        try:
            v = str(eval(v, {"__builtins__": {}}))
        except Exception:
            pass
    try:
        f = float(v)
        v = str(int(f)) if f == int(f) else repr(round(f, 6))
    except ValueError:
        pass
    return v.lower()


def doc_entries(md):
    text = open(md).read()
    for m in re.finditer(r"^#{3,6} --(\S+)", text, re.M):
        name = m.group(1)
        line = text.count("\n", 0, m.start()) + 1
        body = text[m.end(): m.end() + 1500]
        body = re.split(r"^#{3,6} ", body, maxsplit=1, flags=re.M)[0]
        d = re.search(r"^Default:\s*(.*)$", body, re.M)
        default = None
        if d:
            first = re.match(r"`([^`]*)`", d.group(1).strip())
            default = first.group(1) if first else re.sub(r"\s*\(.*$", "", d.group(1).strip())
        yield name, line, default, "deprecated" in body.lower()


def docs_corpus(root):
    out = []
    for dp, _, fs in os.walk(root):
        if "/releases" in dp:
            continue
        for f in fs:
            if f.endswith(".md"):
                out.append(open(os.path.join(dp, f), errors="ignore").read())
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--series", default="stable", help="docs folder under docs/content (default: stable)")
    ap.add_argument("--release", help="e.g. 2026.1.2.0-b137 (default: appVersion of --series)")
    ap.add_argument("--prev", help="previous release to diff flag lists against, e.g. 2025.2.7.0-b107")
    ap.add_argument("--cache", default=".flag_xml_cache")
    ap.add_argument("-o", "--output", help="write the Markdown report here (default: stdout)")
    a = ap.parse_args()

    rel = a.release or release_from_docs(a.series)
    xml = {p: fetch(rel, p, a.cache) for p in PROCS}
    out = [f"# Flag reference audit: docs/content/{a.series} vs {rel}\n"]

    for proc, page in PROCS.items():
        md = f"docs/content/{a.series}/reference/configuration/{page}"
        other = "master" if proc == "tserver" else "tserver"
        rows = {"missing": [], "wrong_process": [], "default": [], "deprecated": []}
        for name, line, ddef, ddep in doc_entries(md):
            loc = f"{md}:{line}"
            f = xml[proc].get(name)
            if f is None:
                key = "wrong_process" if name in xml[other] else "missing"
                rows[key].append(f"| `{name}` | {loc} | {'only in yb-' + other if key == 'wrong_process' else 'not in binary (nonexistent, renamed, or hidden)'} |")
                continue
            if "deprecated" in f["tags"] and not ddep:
                rows["deprecated"].append(f"| `{name}` | {loc} | binary tags it deprecated; doc does not |")
            if ddef is None:
                continue
            if f["default"] is not None:
                if norm(ddef) != norm(f["default"]):
                    rows["default"].append(f"| `{name}` | {loc} | doc `{ddef[:60]}` | binary `{f['default']}` |")
            elif norm(ddef) not in (norm(f["initial"]), norm(f["target"])):
                rows["default"].append(f"| `{name}` | {loc} | doc `{ddef[:60]}` | AutoFlag `{f['initial']}` -> `{f['target']}` |")

        out.append(f"\n## {page} vs {proc} flags\n")
        out.append(f"\n### Default mismatches ({len(rows['default'])})\n\n| Flag | Location | Doc | Binary |\n|---|---|---|---|")
        out += rows["default"]
        out.append(f"\n### Documented on the wrong process page ({len(rows['wrong_process'])})\n\n| Flag | Location | Note |\n|---|---|---|")
        out += rows["wrong_process"]
        out.append(f"\n### Documented but not in the binary ({len(rows['missing'])})\n\n| Flag | Location | Note |\n|---|---|---|")
        out += rows["missing"]
        out.append(f"\n### Deprecated in binary, not marked in doc ({len(rows['deprecated'])})\n\n| Flag | Location | Note |\n|---|---|---|")
        out += rows["deprecated"]

    if a.prev:
        corpus = docs_corpus(f"docs/content/{a.series}")
        prev = {p: fetch(a.prev, p, a.cache) for p in PROCS}
        out.append(f"\n## Flags new since {a.prev} that no {a.series} page mentions\n")
        seen = set()
        for proc in PROCS:
            for name in sorted(set(xml[proc]) - set(prev[proc])):
                f = xml[proc][name]
                if name in seen or name in corpus or "test" in name or "unsafe" in f["tags"]:
                    continue
                seen.add(name)
                dflt = f["default"] if f["default"] is not None else f"{f['initial']} -> {f['target']}"
                out.append(f"- `{name}` ({proc}; default `{dflt}`; tags {','.join(t for t in f['tags'] if t)}): {f['meaning'][:140]}")
        out.append(f"\n## Flags removed since {a.prev} but still in {a.series} docs (outside release notes)\n")
        for proc in PROCS:
            for name in sorted(set(prev[proc]) - set(xml[proc])):
                if name not in seen and re.search(rf"\b{re.escape(name)}\b", corpus):
                    seen.add(name)
                    out.append(f"- `{name}`")

    report = "\n".join(out) + "\n"
    if a.output:
        open(a.output, "w").write(report)
    else:
        sys.stdout.write(report)


if __name__ == "__main__":
    main()
