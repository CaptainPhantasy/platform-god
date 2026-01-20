# WEB APPLICATIONS REPORT
**Generated:** 2026-01-15
**Category:** Web Applications
**Repositories:** 10

---

## 1. FLUX
**Path:** `/Volumes/Storage/FLUX/FLUX`

### Overview
AI-native project management platform with Electron desktop support and rich collaboration features.

### Tech Stack
- **Vite:** Build tool (using rolldown-vite)
- **React:** 18.3.1
- **Electron:** 35.7.5 (desktop app)
- **AI:** Anthropic SDK, Google GenAI, OpenAI
- **Tiptap:** Rich text editor
- **Supabase:** Backend
- **Recharts:** Analytics
- **Framer Motion:** Animations

### Key Features
- Project management
- AI-powered assistance
- Real-time collaboration
- Rich text editing with code blocks
- Desktop application support

### Status Score: 82/100
- **Excellent architecture**
- **Modern tooling**
- **Active development**
- **Good documentation**

### TODOs
- Complete Electron packaging
- Add more AI features
- Implement team collaboration

### Recommendations
- **PRIORITY:** Complete and deploy
- Add user testing
- Implement analytics

---

## 2. Fortune Finder
**Path:** `/Volumes/Storage/Development/Fortune Finder`

### Overview
Geological exploration app with map visualization and geode/cave prediction.

### Tech Stack
- **Vite:** Build tool
- **React:** 19.2.0
- **Mapbox GL:** 3D maps
- **React Map GL:** Map components
- **Google GenAI:** AI predictions
- **Dexie:** IndexedDB wrapper

### Key Features
- 3D map visualization
- Geological data layers
- Image processing for geological features
- GeoJSON data handling

### Status Score: 75/100
- **Niche application**
- **Good map implementation**
- **Interesting AI use case**

### Recommendations
- Add more geological data sources
- Implement sharing features
- Add export functionality

---

## 3. TypeCasting
**Path:** `/Volumes/Storage/Development/TypeCasting`

### Overview
Audio/visual casting application with Tone.js for sound generation.

### Tech Stack
- **Vite:** Latest (7.1.2)
- **React:** 19.1.1
- **Tone.js:** 15.1.22 (audio synthesis)
- **TailwindCSS:** 4.x
- **Recharts:** Visualizations

### Key Features
- Audio synthesis
- Visual casting
- Real-time audio manipulation
- Performance metrics

### Status Score: 70/100
- **Creative application**
- **Good audio implementation**
- **Clean UI**

### Recommendations
- Add recording capability
- Implement presets
- Add MIDI support

---

## 4. assend (LinkedIn Ascension)
**Path:** `/Volumes/Storage/Development/assend`

### Overview
LinkedIn growth platform with AI-powered 30-day missions and content generation.

### Tech Stack
- **Next.js:** 15.5.2
- **React:** 19.1.1
- **OpenAI:** 4.104.0
- **Supabase:** Backend
- **Stripe:** Payments
- **Resend:** Email

### Key Features
- LinkedIn content generation
- 30-day growth missions
- SaaS subscription model
- Progress tracking

### Status Score: 72/100
- **Viable SaaS product**
- **Good monetization**
- **Clear value proposition**

### Notes
- **Duplicates:** assend copy, assend copy 2 exist
- Consider consolidating

### Recommendations
- **MERGE** duplicates into main
- Complete LinkedIn API integration
- Add analytics

---

## 5. weaves
**Path:** `/Volumes/Storage/Development/weaves`

### Overview
Agentic workflow system with OpenAI integration and database management.

### Tech Stack
- **Next.js:** 14.0.4
- **React:** 18
- **OpenAI:** 4.20.1
- **Supabase:** Backend
- **Dexie:** IndexedDB
- **Zustand:** State

### Status Score: 70/100
- **Good architecture**
- **Agent integration**
- **Needs updates** (older Next.js)

### Recommendations
- Update to Next.js 15
- Add more agents
- Implement testing

---

## 6. scanstockpro
**Path:** `/Volumes/Storage/Development/scanstockpro`

### Overview
Barcode scanning inventory management with multi-agent coordination.

### Tech Stack
- **Next.js:** 15.5.2
- **ZXing:** Barcode scanning
- **Supabase:** Backend
- **Stripe:** Payments
- **Recharts:** Analytics
- **React Webcam:** Camera access

### Key Features
- Multi-device barcode scanning
- Real-time inventory sync
- Agent coordination (4 agents)
- Progress tracking

### Status Score: 68/100
- **Niche application**
- **Good multi-device sync**
- **Agent coordination**

### Recommendations
- Add more barcode formats
- Implement offline mode
- Add reporting

---

## 7. legacy_site
**Path:** `/Volumes/Storage/LegacySiteTest/legacy_site`

### Overview
Modern landing page with animations and 3D globe visualization.

### Tech Stack
- **Next.js:** 16.1.0 (latest)
- **React:** 19.2.3
- **Framer Motion:** Animations
- **Cobe:** 3D globe
- **Biome:** Linting
- **TailwindCSS:** Styling

### Status Score: 75/100
- **Modern stack**
- **Beautiful UI**
- **Good animations**

### Recommendations
- Add more content sections
- Implement CMS
- Add analytics

---

## 8. spacegather
**Path:** `/Volumes/Storage/Legacy AI SpaceGather/spacegather`

### Overview
Photogrammetry and 3D space analysis application with computer vision.

### Tech Stack
- **Next.js:** 16.1.0
- **React:** 19.2.0
- **Three.js:** 3D rendering
- **OpenCV.js:** Computer vision (@techstark/opencv-js)
- **Google GenAI:** AI analysis
- **Sharp:** Image processing
- **Jest + Playwright:** Testing

### Key Features
- 3D space reconstruction
- Photogrammetry
- Computer vision analysis
- Comprehensive testing

### Status Score: 78/100
- **Advanced application**
- **Good testing**
- **Innovative use case**

### Recommendations
- Add more analysis features
- Implement export formats
- Add collaboration

---

## 9. rebrand (Zwanzigz Tycoon)
**Path:** `/Volumes/Storage/Development/rebrand`

### Overview
Browser-based tycoon game with sprite management.

### Tech Stack
- **HTML/JavaScript:** Vanilla implementation
- **CSS:** Custom styling
- **No frameworks:** Pure JavaScript

### Key Features
- Sprite extraction
- Game mechanics
- Large sprite datasets (25MB+)

### Status Score: 65/100
- **Simple implementation**
- **Large data files**
- **No modern tooling**

### Notes
- **Duplicate:** rebrand copy exists
- Game appears to be a hobby project

### Recommendations
- Modernize to framework
- Reduce asset sizes
- Add build process

---

## 10. Vanguard
**Path:** `/Volumes/Storage/Vanguard`

### Overview
Hybrid web/Python application with orchestrator backend.

### Tech Stack
- **Frontend:** Vite, React 19.2.3
- **Backend:** Python (vanguard_orchestrator.py)
- **Google GenAI:** 1.35.0
- **Recharts:** Visualizations

### Status Score: 75/100
- **Hybrid architecture**
- **Python backend**
- **Good documentation**

### Recommendations
- Consider consolidating backend
- Add API documentation
- Implement proper deployment

---

## CONSOLIDATION RECOMMENDATIONS

### Immediate Actions

1. **MERGE assend variants**
   ```
   Keep: /Development/assend
   Archive: assend copy, assend copy 2
   ```

2. **MERGE rebrand variants**
   ```
   Evaluate if game is worth keeping
   If yes: Modernize to Vite + React
   If no: Archive
   ```

3. **PRIORITIZE production-ready apps**
   - FLUX (82/100) - Complete and deploy
   - spacegather (78/100) - Unique, finish features
   - legacy_site (75/100) - Add content
   - Vanguard (75/100) - Proper deployment

### Technology Standardization

**Recommended Stack:**
```json
{
  "framework": "Next.js 15+",
  "react": "19.x",
  "styling": "TailwindCSS 4.x",
  "state": "Zustand",
  "ai": "@anthropic-ai/sdk or @google/genai",
  "database": "Supabase",
  "testing": "Vitest + Playwright",
  "build": "Vite/Turbopack"
}
```

---

## FEATURE MATRIX

| App | AI | Maps | Audio | 3D | Payments | Testing | Priority |
|-----|----|----|-------|---|----------|---------|----------|
| FLUX | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | HIGH |
| Fortune Finder | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | MED |
| TypeCasting | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ | LOW |
| assend | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | MED |
| weaves | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | MED |
| scanstockpro | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | LOW |
| legacy_site | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | HIGH |
| spacegather | ✅ | ❌ | ❌ | ✅ | ❌ | ✅ | HIGH |
| rebrand | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | LOW |
| Vanguard | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | MED |

---

## DEPLOYMENT STATUS

| App | Deployed | Domain | Notes |
|-----|----------|--------|-------|
| FLUX | ❌ | TBD | Electron builds needed |
| Fortune Finder | ❌ | TBD | Needs production config |
| TypeCasting | ❌ | TBD | Development only |
| assend | ❌ | TBD | SaaS - needs deployment |
| weaves | ❌ | TBD | Development only |
| scanstockpro | ❌ | TBD | Production-ready |
| legacy_site | ❌ | TBD | Landing page |
| spacegather | ❌ | TBD | Needs optimization |
| rebrand | ❌ | TBD | Hobby project |
| Vanguard | ❌ | TBD | Hybrid deployment |

---

*End of Web Apps Report*
