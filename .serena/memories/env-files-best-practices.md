# ENV FILES - DO NOT EVER FORGET

## .env.local
- **Purpose:** Local development credentials
- **Contents:** REAL API keys, secrets, actual values
- **Git:** MUST BE GITIGNORED
- **Action:** NEVER touch, never modify, never "fix" this file

## .env.example
- **Purpose:** Example configuration template
- **Contents:** Placeholders, example values, documentation
- **Git:** TRACKED in repository
- **Action:** Update this with new variables/docs

## .env
- **Purpose:** Default/base configuration
- **Contents:** Non-sensitive defaults or empty values
- **Git:** Usually gitignored, but can contain safe defaults

## RULES TO LIVE BY
1. Never "fix" an exposed key in .env.local - that's where it belongs
2. .env.local is FOR credentials, not a security issue
3. Only update .env.example with new variable documentation
4. If .env.local is tracked in git, that's the problem to fix - not the file contents

## DON'T BE AN IDIOT
- If you see a real API key in .env.local → **LEAVE IT ALONE**
- That is the CORRECT place for it
- The file should be .gitignored, that's the fix
- NOT "replace the key with a placeholder"
