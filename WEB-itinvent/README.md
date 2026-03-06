# IT-invent Web

Web application for IT equipment inventory management.

## Stack

- **Backend**: Python + FastAPI + pyodbc (SQL Server)
- **Frontend**: React 18 + Vite + Material UI v5
- **Auth**: JWT tokens

## Project Structure

```
it-invent-web/
├── backend/              # FastAPI backend
│   ├── main.py         # Application entry point
│   ├── config.py        # Configuration
│   ├── database/        # SQL queries and connection
│   ├── models/          # Pydantic models
│   ├── api/v1/         # API endpoints
│   └── utils/          # Security, helpers
└── frontend/           # React frontend
    └── src/
        ├── api/          # API client
        ├── components/    # React components
        ├── contexts/      # Auth context
        └── pages/         # Page components
```

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- SQL Server with ITINVENT database

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install fastapi uvicorn[standard] pyodbc python-jose[cryptography] passlib[bcrypt] pydantic[email] python-dotenv

# Configure single env in project root
cd ..
cp .env.example .env
# Edit .env with your database credentials, then return:
cd WEB-itinvent/backend

# Run development server
python -m uvicorn main:app --reload --port 8000
```

Backend will be available at:
- http://localhost:8000
- API docs: http://localhost:8000/docs

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Frontend now reads VITE_* variables from project root .env
# (C:\Project\Image_scan\.env)

# Run development server
npm run dev
```

Frontend will be available at:
- http://localhost:5173

## Default Users

| Username | Password | Role |
|----------|----------|------|
| admin    | admin    | Admin |
| user     | user123  | User  |

**Important**: Change default passwords in production!

## Features

- [x] Authentication (JWT)
- [x] Equipment search by serial number
- [x] Employee search
- [ ] Equipment transfer
- [ ] Work tracking (cartridges, batteries, cleaning)
- [ ] Full database view with pagination
- [ ] Export to Excel
- [ ] Database switching

## API Endpoints

### Authentication
- `POST /api/v1/auth/login` - Login
- `GET /api/v1/auth/me` - Get current user
- `POST /api/v1/auth/logout` - Logout

### Equipment
- `GET /api/v1/equipment/search/serial?q={query}` - Search by serial
- `GET /api/v1/equipment/search/employee?q={query}&page={page}` - Search by employee
- `GET /api/v1/equipment/{inv_no}` - Get by inventory number
- `GET /api/v1/equipment/database?page={page}` - Get all equipment
- `GET /api/v1/equipment/branches` - Get branches
- `GET /api/v1/equipment/locations/{branch_id}` - Get locations

## License

MIT
