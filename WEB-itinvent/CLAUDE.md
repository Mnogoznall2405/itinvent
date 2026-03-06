# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

IT-invent Web is a full-stack web application for IT equipment inventory management. The backend connects to a legacy SQL Server database (ITINVENT) using pyodbc, while the frontend uses React with Material UI.

**Tech Stack:**
- Backend: Python + FastAPI + pyodbc (SQL Server)
- Frontend: React 18 + Vite + Material UI v5 + React Router
- Auth: JWT tokens with Bearer scheme

## Commands

### Backend (from project root)
```bash
# Run backend development server
python -m uvicorn backend.main:app --reload --port 8000
```

Backend API docs available at http://localhost:8000/docs

### Frontend
```bash
cd frontend
npm install           # Install dependencies
npm run dev          # Development server (http://localhost:5173)
npm run build        # Production build
npm run preview      # Preview production build
```

## Architecture

### Backend Structure

**Entry Point:** [backend/main.py](backend/main.py) - FastAPI app with CORS, exception handlers, and router includes

**Configuration:** [backend/config.py](backend/config.py) - Loads from [backend/.env](backend/.env) using dataclasses
- `DatabaseConfig`: SQL Server connection (ODBC)
- `JWTConfig`: Token settings (8-hour default expiry)
- `AppConfig`: CORS origins, debug mode

**Database Layer:** [backend/database/connection.py](backend/database/connection.py)
- `DatabaseConnectionManager`: Context manager for SQL Server connections with autocommit/rollback
- `get_database_config(db_id)`: Supports dynamic database switching via env vars (`DB_{DB_ID}_*`)
- `get_db(db_id)`: FastAPI dependency for database manager
- `set_user_database()` / `get_user_database()`: In-memory per-user database selection

**Authentication:** [backend/api/deps.py](backend/api/deps.py)
- `get_current_user`: JWT Bearer token dependency
- `get_current_user_optional`: Optional auth for endpoints
- `get_current_database_id`: Gets user's selected database

**API Routes:**
- [backend/api/v1/auth.py](backend/api/v1/auth.py) - Login, logout, change password
- [backend/api/v1/equipment.py](backend/api/v1/equipment.py) - Equipment search by serial, employee, inventory number
- [backend/api/v1/database.py](backend/api/v1/database.py) - Database switching, full database view with pagination

**Models:** [backend/models/](backend/models/) - Pydantic models (auth.py for User, equipment.py for equipment)

### Frontend Structure

**Entry Point:** [frontend/src/main.jsx](frontend/src/main.jsx) - React app mount with ReactDOM

**Routing:** [frontend/src/App.jsx](frontend/src/App.jsx)
- `ProtectedRoute` wrapper for authenticated routes
- `/login` (public), `/database`, `/settings` (protected)

**State Management:** [frontend/src/contexts/AuthContext.jsx](frontend/src/contexts/AuthContext.jsx)
- `AuthProvider` manages user state in localStorage
- `useAuth()` hook for login/logout/auth check

**API Client:** [frontend/src/api/client.js](frontend/src/api/client.js)
- Axios instance with base URL from `VITE_API_URL` env var
- Request interceptor adds Bearer token
- Response interceptor handles 401 redirects
- `authAPI` and `equipmentAPI` method collections

**Pages:** [frontend/src/pages/](frontend/src/pages/)
- `Login.jsx`, `Database.jsx`, `Search.jsx`, `Transfer.jsx`, `Work.jsx`, `Settings.jsx`

**Components:** [frontend/src/components/](frontend/src/components/)
- `layout/MainLayout.jsx` - Main app layout

## Key Patterns

### Database Queries
All SQL queries use parameterized `?` placeholders (pyodbc style). Results returned as list of dicts with column names as keys.

### Dynamic Database Switching
Users can switch databases (e.g., ITINVENT, MSK-ITINVENT) via settings. Database config fetched from environment variables:
- Default: `SQL_SERVER_HOST`, `SQL_SERVER_DATABASE`, etc.
- Per-database: `DB_{DB_ID}_HOST`, `DB_{DB_ID}_DATABASE`, etc.

### API Response Format
All endpoints return JSON. Errors use FastAPI's `HTTPException` with `detail` field.

## Default Users

| Username | Password | Role |
|----------|----------|------|
| admin    | admin    | Admin |
| user     | user123  | User  |

---

# JSON Data Files

## Overview

The web application works with JSON data files located in the parent `data/` directory. These files are shared with the Telegram bot and contain all the equipment, employee, and operation data.

## Data Location

**Path from web backend:** `../data/` (relative to `WEB-itinvent/backend/`)
**Absolute path:** `C:/Project/Image_scan/data/`

## JSON Files Structure

| File | Purpose | Key Fields |
|------|---------|------------|
| `cartridge_database.json` | Cartridge database for printer model matching | manufacturer, model, cartridges |
| `equipment_transfers.json` | Equipment transfer records | inv_no, serial, from_employee, to_employee, date |
| `unfound_equipment.json` | Equipment not found in main database | serial, employee, type, model, location |
| `pc_cleanings.json` | PC cleaning operations | serial, employee, date, branch, location |
| `cartridge_replacements.json` | Cartridge replacement records | serial, printer_model, color, date |
| `battery_replacements.json` | Battery replacement records | serial, date, branch, location |
| `component_replacements.json` | PC component replacements | serial, component_type, date |
| `user_db_selection.json` | User database selection preferences | user_id, selected_database |
| `printer_color_cache.json` | Cache for printer color detection | serial, color |
| `printer_component_cache.json` | Cache for printer component detection | serial, components |
| `equipment_installations.json` | Equipment installation records | inv_no, serial, employee, date |

## Data Access Pattern

When working with JSON files in the web backend:

```python
from pathlib import Path

# Path to data directory (parent of WEB-itinvent)
DATA_DIR = Path(__file__).parent.parent.parent / "data"

# Example: Load cartridge database
cartridge_db_file = DATA_DIR / "cartridge_database.json"
```

## Shared Data with Telegram Bot

**Important:** The web application shares these JSON files with the Telegram bot. Any changes made through the web interface will be visible to bot users, and vice versa.

**Concurrency consideration:** When implementing write operations, consider file locking or atomic writes to prevent data corruption when both bot and web app write simultaneously.

---

# Design System

## Overview

All pages use a unified Material UI design system optimized for mobile devices and touch interactions.

## Theme Configuration

**File:** `frontend/src/theme/index.js`

The theme is created using Material UI's `createTheme` with custom tokens.

### Color Palette

| Color | Purpose | Value |
|-------|---------|--------|
| Primary | Brand color, primary actions | #1976d2 |
| Secondary | Accents, secondary actions | #00796b |
| Background | App background | #f5f7fa |
| Surface | Cards, dialogs | #ffffff |
| Error | Destructive actions, errors | #d32f2f |
| Warning | Warnings | #ed6c02 |
| Success | Success states | #2e7d32 |

### Typography

- **Font Family:** System font stack (-apple-system, Segoe UI, Roboto, etc.)
- **Base Size:** 14px on mobile, 16px on desktop
- **Scale:** Mobile-first with responsive adjustments

### Spacing

- **Base Unit:** 8px
- **Touch Targets:** Minimum 44×44px for mobile
- **Desktop Targets:** 36×36px minimum

### Component Overrides

Key component overrides in theme:

- **Paper:** No background image (performance), consistent elevation
- **Button:** Minimum 44px height (mobile), no uppercase
- **TextField:** Outlined variant, proper hitbox
- **IconButton:** 44×44px on mobile
- **Table:** Responsive padding and font sizes
- **Checkbox:** 32×32px on mobile (24×24px desktop)
- **Dialog:** Full width with margin on mobile
- **Tabs:** Wider touch targets on mobile

## Global Styles

**File:** `frontend/src/index.css`

Global styles include:
- CSS reset with border-box sizing
- Custom scrollbar styling
- Focus styles for accessibility
- Touch action manipulation
- Safe area handling for notched devices
- Print styles

## Usage in Components

```jsx
import { ThemeProvider } from '@mui/material/styles'
import theme from './theme'

// Theme is applied at root in main.jsx
// All components have access via sx prop or useStyles
```

## Design Patterns

### 1. Mobile-First
- Design for mobile (320px+) first
- Progressive enhancement for larger screens
- Touch-friendly targets (44px minimum)

### 2. Visual Hierarchy
- Use font weight and size for emphasis
- Color sparingly for accents only
- Spacing to group related items

### 3. Interactive States
- Hover states for desktop
- Active/pressed states for touch
- Loading states for async actions
- Error states for validation

### 4. Accessibility
- Focus indicators on all interactive elements
- ARIA labels on icon-only buttons
- Keyboard navigation support
- Screen reader friendly

## Component Styling Guidelines

### Tables (Data Grid)
- Use `size="small"` for mobile
- Add checkbox column for selection
- Responsive padding (12px → 8px on mobile)
- Sticky headers for long lists
- `userSelect: "none"` on rows to prevent text selection

### Forms
- Use outlined variant for better visibility
- Add helper text for context
- Group related fields with Cards or Paper
- Validation colors: error (red), warning (orange), success (green)

### Buttons
- Primary: For main actions
- Secondary/Text: For secondary actions
- Icon: For toolbar actions
- Minimum 44px height on mobile

### Cards/Paper
- elevation 2 by default
- elevation 4 on hover
- 8px border radius
- Proper padding (16px mobile, 24px desktop)
