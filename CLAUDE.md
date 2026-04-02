# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**doc_revewer** is a document review tool with a React frontend and Python backend. The system allows users to upload documents and review them against configurable standards using AI-powered multi-agent workflows.

## Architecture

```
doc_revewer/
├── frontend/     # React + Vite + TypeScript (custom CSS, no Tailwind)
└── backend/      # Python FastAPI server with AgentScope
```

## Frontend Structure

The frontend (`frontend/src/App.tsx`) is a **monolithic single-file** React application with:
- **Login system** with role-based auth (admin/user)
- **Pages**: Login, 发起审查 (ReviewCreate), 我的任务 (MyTasks), 任务详情, 结果页, 标准管理, 模型配置, 规则管理, 全站任务, 导出中心
- **API Client**: Axios-based with token auth, base URL configurable via `VITE_API_BASE_URL`
- **Routes**: React Router v7 with nested routes

### Key Types
```typescript
type Task = {
  task_id: string
  doc_name?: string
  standard_id?: string
  status: string
  current_stage: string
  overall_progress: number
  failed_rules: number
}

type UserInfo = {
  user_id: string
  role: 'admin' | 'user'
}
```

## Backend Architecture

The backend uses **AgentScope** for multi-agent orchestration. Key components:

- **API Layer** (`backend/api/v1/`): FastAPI routers for auth, standards, review_tasks, results, admin
- **Agents** (`backend/agents/`): Specialized LLM agents for document review
  - `pdf_parser_agent.py` - Extracts text/content from PDFs
  - `rule_extractor_agent.py` - Extracts review rules from standards
  - `rule_classifier_agent.py` - Classifies document content against rules
  - `document_reviewer_agent.py` - Main review orchestration
  - `orchestrator_agent.py` - Coordinates the review workflow
- **Database** (`backend/db/`, `backend/models/`): SQLAlchemy with SQLite
- **Runtime** (`backend/agentscope_runtime.py`): AgentScope initialization and task management

### AgentScope Integration

The backend integrates with AgentScope Studio for tracing and monitoring. Key environment variables:
- `AGENTSCOPE_STUDIO_URL` - AgentScope Studio URL for traces
- `AGENTSCOPE_TRACE_DIAG=1` - Enable diagnostic traces (useful for debugging)

## Commands

### Frontend
```bash
cd frontend
npm install          # Install dependencies
npm run dev          # Start dev server (port 5173)
npm run build        # Production build
npm run lint         # Lint code
```

### Backend
```bash
cd backend
pip install -r requirements.txt   # Install dependencies
python main.py                    # Start server (port 18000)
```

### Running the Application
```bash
# Terminal 1: Start backend
cd backend && python main.py

# Terminal 2: Start frontend
cd frontend && npm run dev
```

## API Endpoints

The backend provides these endpoints:
- `POST /api/v1/auth/login` - Login with username + role
- `GET /api/v1/me` - Get current user info
- `GET /api/v1/standards` - List review standards
- `POST /api/v1/review-tasks` - Create review task (multipart form)
- `GET /api/v1/review-tasks` - List user's tasks
- `GET /api/v1/review-tasks/:id` - Get task details
- `GET /api/v1/results/:task_id` - Get review results
- Admin: standards, model-providers, tasks, exports management endpoints

## Environment Variables

- `VITE_API_BASE_URL` - Frontend: Backend API base URL (default: `http://127.0.0.1:18000/api/v1`)
- `AGENTSCOPE_STUDIO_URL` - Backend: AgentScope Studio URL for traces
- `AGENTSCOPE_TRACE_DIAG=1` - Backend: Enable trace diagnostics

## Development Notes

- The frontend API client is in `frontend/src/api/client.ts`
- Authentication uses JWT tokens stored in localStorage
- Backend uses python-jose for JWT and passlib for password hashing
- PDF processing uses pdfplumber, PyMuPDF, Pillow, and pytesseract
- AgentScope status endpoint: `GET /api/v1/agentscope/status` (debugging)