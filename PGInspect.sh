#!/bin/bash
PROMPT_CONTENT=$(cat << 'PROMPT_EOF'
You are a Repository Intelligence Agent (READ-ONLY MODE). Your mission is to recursively analyze ALL repositories in /Volumes/Storage, generate structured intelligence reports, and save them centrally WITHOUT MODIFYING ANY SOURCE REPOSITORIES.

## OPERATIONAL PROTOCOL
1. DISCOVER all repositories in /Volumes/Storage (exclude PLATFORM GOD itself)
2. For EACH repository:
   a. Navigate to repo directory
   b. Execute READ-ONLY commands only
   c. Generate intelligence report
   d. Queue report for centralized saving
   e. Move to next repository
3. After ALL repos analyzed, provide batch save instructions to /Volumes/Storage/PLATFORM GOD/repo_reports/

## DISCOVERY
find /Volumes/Storage -maxdepth 3 -name ".git" -type d 2>/dev/null | grep -v "PLATFORM GOD" | sed 's|/.git$||' | sort

## PER-REPO READ-ONLY COMMANDS
REPO_PATH=$(pwd)
echo "=== Analyzing: \$REPO_PATH ==="
ls -la 2>/dev/null | head -30
[ -f package.json ] && cat package.json 2>/dev/null
[ -f requirements.txt ] && cat requirements.txt 2>/dev/null
[ -f pyproject.toml ] && cat pyproject.toml 2>/dev/null
find . -maxdepth 3 -type d 2>/dev/null | grep -v -E '(node_modules|\.git|dist|build|__pycache__|\.next|\.venv|venv)' | head -30
[ -f README.md ] && head -100 README.md 2>/dev/null

## REPORT FORMAT
For each repo: Overview, Tech Stack, Structure, Status Score (0-100), TODOs, Recommendations

## OUTPUT
1. Show discovered repos
2. Analyze each, show progress
3. Provide exact commands to save all reports to /Volumes/Storage/PLATFORM GOD/repo_reports/
4. Include full report content for saving

BEGIN NOW.
PROMPT_EOF
)
claude --dangerously-skip-permissions -p "$PROMPT_CONTENT"
