from unidiff import PatchSet
from io import StringIO
from typing import Optional


# ── Parse unified diff ────────────────────────────────────────────────────────

def parse_diff(diff_text: str) -> dict:
    """
    Parse a GitHub unified diff into structured Python objects.
    Called by webhook worker after fetching PR diff.

    Returns:
    {
        files: [
            {
                path:         str,
                status:       added | modified | deleted,
                additions:    int,
                deletions:    int,
                added_lines:  [{ line_number, content }],
                removed_lines:[{ line_number, content }],
                hunks:        [{ header, lines }],
            }
        ],
        total_additions: int,
        total_deletions: int,
        total_files:     int,
    }
    """
    if not diff_text or not diff_text.strip():
        return _empty_result()

    try:
        patch = PatchSet(StringIO(diff_text))
    except Exception as e:
        return _empty_result(error=str(e))

    files = []
    total_additions = 0
    total_deletions = 0

    for patched_file in patch:
        file_result = _parse_file(patched_file)
        files.append(file_result)
        total_additions += file_result["additions"]
        total_deletions += file_result["deletions"]

    return {
        "files":           files,
        "total_additions": total_additions,
        "total_deletions": total_deletions,
        "total_files":     len(files),
        "error":           None,
    }


# ── Parse single file ─────────────────────────────────────────────────────────

def _parse_file(patched_file) -> dict:
    """Parse a single file from the patch."""

    # determine file status
    if patched_file.is_added_file:
        status = "added"
        path   = patched_file.path
    elif patched_file.is_removed_file:
        status = "deleted"
        source = patched_file.source_file
        path = source[2:] if source.startswith("a/") else source
    else:
        status = "modified"
        path   = patched_file.path

    added_lines   = []
    removed_lines = []
    hunks         = []

    for hunk in patched_file:
        hunk_lines = []

        for line in hunk:
            if line.is_added:
                added_lines.append({
                    "line_number": line.target_line_no,
                    "content":     line.value.rstrip("\n"),
                })
                hunk_lines.append({
                    "type":        "added",
                    "line_number": line.target_line_no,
                    "content":     line.value.rstrip("\n"),
                })

            elif line.is_removed:
                removed_lines.append({
                    "line_number": line.source_line_no,
                    "content":     line.value.rstrip("\n"),
                })
                hunk_lines.append({
                    "type":        "removed",
                    "line_number": line.source_line_no,
                    "content":     line.value.rstrip("\n"),
                })

            else:
                # context line — unchanged
                hunk_lines.append({
                    "type":        "context",
                    "line_number": line.target_line_no,
                    "content":     line.value.rstrip("\n"),
                })

        hunks.append({
            "header": str(hunk.section_header).strip(),
            "lines":  hunk_lines,
        })

    return {
        "path":          path,
        "status":        status,
        "additions":     len(added_lines),
        "deletions":     len(removed_lines),
        "added_lines":   added_lines,
        "removed_lines": removed_lines,
        "hunks":         hunks,
    }


# ── Extract changed files list ────────────────────────────────────────────────

def get_changed_files(diff_text: str) -> list[str]:
    """
    Quick helper — just return list of changed file paths.
    Used by LLM to know which files to focus on.
    """
    result = parse_diff(diff_text)
    return [f["path"] for f in result["files"]]


# ── Extract changed lines for a specific file ─────────────────────────────────

def get_file_changes(diff_text: str, file_path: str) -> Optional[dict]:
    """
    Get changes for a specific file only.
    Used when reviewing a single file.
    """
    result = parse_diff(diff_text)
    for f in result["files"]:
        if f["path"] == file_path:
            return f
    return None


# ── Format diff for LLM prompt ────────────────────────────────────────────────

def format_diff_for_prompt(parsed: dict, max_lines: int = 200) -> str:
    """
    Format parsed diff into clean text for LLM prompt.
    Limits total lines to avoid exceeding token budget.
    """
    if not parsed["files"]:
        return "No changes found."

    parts = []
    line_count = 0

    files_processed = 0
    for file in parsed["files"]:
        files_processed += 1
        if line_count >= max_lines:
            remaining = max(parsed["total_files"] - files_processed + 1, 0)
            parts.append(f"... {remaining} more files truncated")
            break

        status_label = {
            "added":    "NEW FILE",
            "deleted":  "DELETED",
            "modified": "MODIFIED",
        }.get(file["status"], "CHANGED")

        parts.append(f"\n--- {file['path']} [{status_label}] ---")
        parts.append(
            f"+{file['additions']} additions, "
            f"-{file['deletions']} deletions"
        )

        for hunk in file["hunks"]:
            if line_count >= max_lines:
                break

            if hunk["header"]:
                parts.append(f"\n@@ {hunk['header']} @@")

            for line in hunk["lines"]:
                if line_count >= max_lines:
                    parts.append("... truncated")
                    break

                prefix = {
                    "added":   "+",
                    "removed": "-",
                    "context": " ",
                }.get(line["type"], " ")

                parts.append(f"{prefix} {line['content']}")
                line_count += 1

    return "\n".join(parts)


# ── Summary for webhook handler ───────────────────────────────────────────────

def get_diff_summary(diff_text: str) -> dict:
    """
    Quick summary of a diff.
    Used by webhook handler to log what changed.
    """
    parsed = parse_diff(diff_text)
    return {
        "total_files":     parsed["total_files"],
        "total_additions": parsed["total_additions"],
        "total_deletions": parsed["total_deletions"],
        "changed_files":   get_changed_files(diff_text),
        "has_changes":     parsed["total_files"] > 0,
    }


# ── Empty result helper ───────────────────────────────────────────────────────

def _empty_result(error: Optional[str] = None) -> dict:
    return {
        "files":           [],
        "total_additions": 0,
        "total_deletions": 0,
        "total_files":     0,
        "error":           error,
    }