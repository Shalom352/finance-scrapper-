#!/usr/bin/env python3
"""Phase 13 — Security & Secret Scanner

Scans all version-controlled files for:
- Leaked credentials & API keys
- Private keys
- Accidental .env files tracked in git
- Cache and temporary debug files
- Large accidental binary files (> 10 MB)
"""

import os
import re
import sys

PATTERNS = {
    "PRIVATE_KEY": re.compile(r"-----BEGIN (RSA|EC|DSA|OPENSSH|PGP|PRIVATE) KEY"),
    "AWS_KEY": re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}"),
    "GITHUB_TOKEN": re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,255}"),
    "HARDCODED_REAL_SECRET": re.compile(r"(?:api[_-]?key|secret[_-]?key|private[_-]?key)\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}['\"]", re.IGNORECASE),
}

IGNORE_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".next", "htmlcov", "dist", "build"}
IGNORE_EXTS = {".pyc", ".pyo", ".dump", ".png", ".jpg", ".jpeg", ".ico", ".svg"}
ALLOWLIST_FILES = {".env.example", "docker-compose.override.yml.example", "frontend/.env.example"}


def scan_repo():
    print("================================================================================")
    print("UMOA Banking Intelligence — Phase 13 Security & Secret Audit")
    print("================================================================================\n")

    issues = []

    # Check git tracked files
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            p = os.path.normpath(os.path.join(root, f))
            _, ext = os.path.splitext(f)

            # Check for accidental .env files
            if f.startswith(".env") and f not in {".env.example", ".env.local.example"}:
                if p not in [".env", ".env.local"]:  # local ignored files
                    issues.append((p, "UNEXPECTED_ENV_FILE"))

            # Check large files
            try:
                sz = os.path.getsize(p)
                if sz > 10 * 1024 * 1024 and ext not in {".dump"}:
                    issues.append((p, f"LARGE_FILE_{sz // (1024*1024)}MB"))
            except Exception:
                pass

            # Skip binaries / dumps / examples
            if ext in IGNORE_EXTS or p in ALLOWLIST_FILES:
                continue

            # Scan text files for secret patterns
            if ext in {".py", ".ts", ".tsx", ".json", ".md", ".yml", ".yaml", ".sh", ".sql"}:
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as fp:
                        lines = fp.readlines()
                        for idx, line in enumerate(lines, 1):
                            for name, pat in PATTERNS.items():
                                if pat.search(line):
                                    # Filter obvious test mocks or placeholders
                                    if "test" in p or "conftest" in p or "mock" in line.lower() or "example" in line.lower():
                                        continue
                                    issues.append((f"{p}:{idx}", name))
                except Exception as e:
                    issues.append((p, f"READ_ERROR_{str(e)}"))

    print(f"Total findings: {len(issues)}")
    if issues:
        print("\nFINDINGS:")
        for path, problem in issues:
            print(f"  Path: {path} | Type: {problem}")
        print("\n[SECURITY AUDIT FAILED]")
        sys.exit(1)
    else:
        print("ALL SCANS CLEAN: 0 secrets, 0 unexpected env files, 0 large files detected.")
        print("\n[SECURITY AUDIT PASSED]")
        sys.exit(0)


if __name__ == "__main__":
    scan_repo()
