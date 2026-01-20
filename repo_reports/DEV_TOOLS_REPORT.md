# DEVELOPER TOOLS REPORT
**Generated:** 2026-01-15
**Category:** Developer Tools
**Repositories:** 6

---

## 1. nanocoder-source
**Path:** `/Volumes/Storage/FLUX/nanocoder-source`

### Overview
Local-first CLI coding agent that brings agentic coding tools to local models or controlled APIs.

### Tech Stack
- **TypeScript:** Primary language
- **Node.js:** Runtime (>=20)
- **Ink:** React CLI framework
- **AI:** Multiple providers (Ollama, OpenRouter, OpenAI)
- **MCP:** Model Context Protocol SDK
- **VSCode Extension:** Included

### Key Features
- Local model support (Ollama, llama-cpp)
- API provider support (OpenRouter, OpenAI)
- VSCode integration
- CLI with rich UI
- File editing capabilities

### Structure
```
├── source/           # Source code
│   ├── app/          # Application logic
│   ├── cli/          # CLI commands
│   └── prompts/      # Agent prompts
├── plugins/vscode/   # VSCode extension
├── dist/             # Compiled output
└── assets/           # Build artifacts
```

### Status Score: 85/100
- **Production-ready**
- **Well-maintained** (v1.17.3)
- **Good documentation**
- **Active development**

### TODOs
- Add more model providers
- Improve error handling
- Add more VSCode features

### Recommendations
- **DEPLOY** as primary local coding tool
- Create installation scripts
- Add team sharing features

---

## 2. FLOYD_CLI (sysc_src)
**Path:** `/Volumes/Storage/FLOYD_CLI/sysc_src`

### Overview
Go-based TUI (Terminal UI) tool for development workflow management.

### Tech Stack
- **Go:** Primary language
- **TUI:** Terminal UI framework
- **CLI:** Command-line interface

### Key Features
- Animations (ASCII art)
- TUI interface
- Modular command system
- Cross-platform support

### Status Score: 85/100
- **Production-ready**
- **Excellent documentation**
- **Active development**
- **Good architecture**

### Structure
```
├── cmd/              # CLI commands
├── tui/              # Terminal UI
├── assets/           # Assets/fonts
├── animations/       # ASCII animations
├── examples/         # Usage examples
└── demos/            # Demo scripts
```

### Recommendations
- **DEPLOY** as team tool
- Add plugin system
- Create package managers (Homebrew, AUR)

---

## 3. dev-launcher
**Path:** `/Volumes/Storage/Development/dev-launcher`

### Overview
Desktop application launcher for development projects with GUI.

### Tech Stack
- **Node.js:** Backend
- **Frontend:** Web technologies
- **Desktop:** Native wrapper

### Key Features
- Project launching
- Environment management
- Desktop integration
- Icon support

### Status Score: 72/100
- **Useful utility**
- **Good documentation** (SSOT files)
- **Needs polish**

### Recommendations
- **COMPLETE** implementation
- Add project templates
- Add quick actions

---

## 4. Foundry
**Path:** `/Volumes/Storage/Foundry`

### Overview
High-performance software factory monorepo with Turborepo for efficient builds.

### Tech Stack
- **Turborepo:** Monorepo management
- **pnpm:** Package manager
- **TypeScript:** Primary language
- **Supabase:** Backend services

### Structure
```
├── apps/             # Applications
├── packages/         # Shared packages
├── supabase/         # Database/functions
├── docs/             # Documentation
└── scripts/          # Build scripts
```

### Status Score: 75/100
- **Good monorepo structure**
- **Modern tooling**
- **Well-documented**

### TODOs
- Add more apps
- Implement CI/CD
- Add shared packages

### Recommendations
- **USE** as primary monorepo template
- Add more packages
- Create app scaffolding

---

## 5. 317Leads
**Path:** `/Volumes/Storage/Development/317Leads`

### Overview
Plumbing leads web application with Google scraping and Cloudflare D1 database.

### Tech Stack
- **Cloudflare Workers:** Edge computing
- **Hono:** Web framework
- **D1:** SQL database
- **React:** Frontend
- **Google APIs:** Scraping

### Key Features
- Lead scraping from Google
- Facility manager data
- CSV export
- Database migrations

### Status Score: 70/100
- **Niche application**
- **Good tech choices**
- **Active development**

### Recommendations
- Add more data sources
- Implement data enrichment
- Add API access

---

## 6. rag-context-system
**Path:** `/Volumes/Storage/Development/rag-context-system`

### Overview
Secure RAG system with document management, Pinecone vector database, and OpenAI embeddings.

### Tech Stack
- **FastAPI:** Python backend
- **Pinecone:** Vector database
- **OpenAI:** Embeddings
- **PostgreSQL:** Document storage
- **Redis:** Caching
- **Google Cloud Storage:** File storage

### Key Features
- Document upload/processing
- PDF, DOCX, Excel support
- Chunking strategies
- Vector search
- Confidence scoring

### Status Score: 68/100
- **Good architecture**
- **Multiple improvements** noted
- **Needs optimization**

### TODOs
- Optimize chunking
- Improve confidence scoring
- Add more document types

### Recommendations
- **MERGE** with other RAG implementations
- Use as reference for RAG patterns
- Add more testing

---

## CONSOLIDATION RECOMMENDATIONS

### High Priority Tools

1. **nanocoder-source** (85/100)
   - Deploy as team standard
   - Create installation guide
   - Add custom prompts

2. **FLOYD_CLI** (85/100)
   - Package for distribution
   - Add to team toolbelt
   - Create aliases for common tasks

3. **Foundry** (75/100)
   - Use as monorepo template
   - Add app scaffolding
   - Create shared component library

### Medium Priority

4. **dev-launcher** (72/100)
   - Complete implementation
   - Add to Foundry as app
   - Create project templates

5. **317Leads** (70/100)
   - Complete data sources
   - Add API access
   - Consider as SaaS

### Low Priority / Archive

6. **rag-context-system** (68/100)
   - Merge with Lighthouse/atlas-rag-teammate
   - Extract best practices
   - Archive original

---

## TOOLCHAIN INTEGRATION

### Recommended Development Setup

```bash
# 1. Monorepo Structure (Foundry)
foundry/
├── apps/
│   ├── nanocoder/      # Local AI coding
│   ├── floyd/          # CLI operations
│   └── launcher/       # Dev launcher GUI
├── packages/
│   ├── shared-ui/      # Common components
│   ├── ai-providers/   # AI integrations
│   └── database/       # Database utilities
└── scripts/
    ├── scaffold/       # App scaffolding
    └── deploy/         # Deployment scripts

# 2. Installation
pnpm install
pnpm dev                # Start all apps

# 3. Development Workflow
floyd new app           # Create new app
nanocoder ./app         # AI-assisted coding
launcher                # GUI for project mgmt
```

---

## TOOL COMPARISON

| Tool | Language | Use Case | Maturity | Recommend |
|------|----------|----------|----------|-----------|
| nanocoder | TypeScript | Local AI coding | High | ✅ YES |
| FLOYD_CLI | Go | CLI automation | High | ✅ YES |
| dev-launcher | Node.js | Project mgmt | Medium | ✅ YES |
| Foundry | TypeScript | Monorepo | Medium | ✅ YES |
| 317Leads | Workers + React | Lead gen | Medium | ⚠️ Niche |
| RAG System | Python | RAG backend | Medium | ⚠️ Duplicate |

---

## INSTALLATION COMMANDS

```bash
# nanocoder
npm install -g @nanocollective/nanocoder
# or build from source in /Volumes/Storage/FLUX/nanocoder-source

# FLOYD_CLI
cd /Volumes/Storage/FLOYD_CLI && ./install.sh
# or from sysc_src: go install ./cmd/floyd

# Foundry
cd /Volumes/Storage/Foundry
pnpm install
pnpm dev

# dev-launcher
cd /Volumes/Storage/Development/dev-launcher
./start.sh
```

---

## DEVELOPMENT ROADMAP

### Phase 1: Tool Consolidation (Week 1)
1. Set up Foundry monorepo
2. Move nanocoder to packages/
3. Integrate FLOYD_CLI
4. Add dev-launcher as app

### Phase 2: Integration (Week 2)
1. Create shared AI provider package
2. Build unified CLI interface
3. Add project scaffolding
4. Implement testing

### Phase 3: Deployment (Week 3)
1. Package for distribution
2. Create documentation site
3. Set up CI/CD
4. Team onboarding

---

*End of Developer Tools Report*
