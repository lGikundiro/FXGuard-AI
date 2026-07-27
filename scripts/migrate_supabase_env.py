"""Safely move a misplaced Supabase database URL to SUPABASE_DB_URL."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def replace_or_add(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"{key}="
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{value}"
            return lines
    lines.append(f"{prefix}{value}")
    return lines


def migrate() -> None:
    if not ENV_PATH.exists():
        raise FileNotFoundError(ENV_PATH)

    text = ENV_PATH.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    values = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in lines
        if "=" in line and not line.lstrip().startswith("#")
    }
    current = values.get("SUPABASE_URL", "").strip()
    parsed = urlparse(current)
    if parsed.scheme == "https" and (parsed.hostname or "").endswith(".supabase.co"):
        lines = replace_or_add(lines, "AUTH_METHODS", "email")
        lines = replace_or_add(lines, "AUTH_SELF_DELETE_RPC", "true")
        ENV_PATH.write_text(newline.join(lines) + newline, encoding="utf-8")
        print("Supabase environment already uses the HTTPS project API URL.")
        return
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("SUPABASE_URL is neither a Supabase API URL nor a PostgreSQL URL.")

    username = parsed.username or ""
    project_reference = username.split(".", 1)[1] if "." in username else ""
    if not project_reference:
        raise ValueError("Could not derive the Supabase project reference safely.")

    lines = replace_or_add(lines, "SUPABASE_DB_URL", current)
    lines = replace_or_add(
        lines,
        "SUPABASE_URL",
        f"https://{project_reference}.supabase.co",
    )
    lines = replace_or_add(lines, "AUTH_METHODS", "email")
    lines = replace_or_add(lines, "AUTH_SELF_DELETE_RPC", "true")
    ENV_PATH.write_text(newline.join(lines) + newline, encoding="utf-8")
    print("Supabase environment migrated without displaying secret values.")


if __name__ == "__main__":
    migrate()
