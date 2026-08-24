# 🛡️ PRGuard: Codebase Learning Assistant

PRGuard is a powerful, AI-driven codebase assistant designed to help developers understand complex repositories, analyze issues, and accelerate their contribution workflow. By leveraging RAG (Retrieval-Augmented Generation) and the latest LLMs, PRGuard provides deep insights into your code and GitHub issues.

## 🚀 What it does

- **AI Codebase Chat**: Ask questions about your entire codebase and get context-aware answers.
- **RAG-Powered Context**: Automatically retrieves relevant code snippets to ground AI responses.
- **Issue Analysis**: Get step-by-step fix guides and root cause analysis for GitHub issues.
- **Repo Visualization**: Interactive charts and file breakdowns to understand project structure.
- **Developer Workflow Tools**: Export prompts for ChatGPT, generate full issue reports, and track "Working On" status.

## 🛠️ Tech Stack

- **Backend**: FastAPI (Python 3.10+), SQLAlchemy, Alembic
- **Frontend**: React, Vite, Vanilla CSS
- **Database**: PostgreSQL (Supabase/Neon), Redis (for rate limiting)
- **AI/ML**: Gemini 1.5 Pro, Anthropic Claude, OpenAI GPT-4o
- **Search/RAG**: ChromaDB (Vector DB) for semantic search

## ✨ Features

- 🔗 **GitHub Integration**: Connect any public or private repository with a single click.
- 🧠 **RAG-powered AI Chat**: Contextual chat that knows your code.
- 📊 **Issue Visualization**: AI-powered analysis of issues with severity and effort estimation.
- 📝 **Report Generation**: One-click "Generate & Copy Report" for full issue summaries.
- ⚡ **Optimistic UI**: Instant feedback when marking issues as "Working On".
- 💬 **Export for ChatGPT**: Pre-formatted prompts for external AI assistance.
- 🌈 **Responsive Design**: Modern, premium UI with full dark mode support.

## 🏁 Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+
- PostgreSQL
- Redis

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/AnirudhSGopal/repolearner.git
   cd repolearner
   ```

2. **Backend Setup**
   ```bash
   cd PRCode/backend
   python -m venv venv
   source venv/bin/activate  # Windows: .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Frontend Setup**
   ```bash
   cd ../frontend
   npm install
   ```

4. **Environment Configuration**
   Copy `.env.example` to `.env` in the root and fill in your keys:
   ```bash
   cp .env.example .env
   ```

5. **Run the Application**
   ```bash
   # Terminal 1 (Backend)
   cd PRCode/backend
   python run.py

   # Terminal 2 (Frontend)
   cd PRCode/frontend
   npm run dev
   ```

## ⚙️ Environment Variables

Please refer to [.env.example](.env.example) for a full list of required variables, including LLM API keys and GitHub OAuth credentials.

## 📂 Project Structure

```text
repolearner/
├── PRCode/
│   ├── backend/            # FastAPI Application
│   │   ├── app/
│   │   │   ├── models/     # SQLAlchemy Models
│   │   │   ├── routes/     # API Endpoints
│   │   │   └── services/   # RAG & LLM Logic
│   │   └── run.py
│   └── frontend/           # React Application
│       ├── src/
│       │   ├── components/ # Reusable UI Components
│       │   ├── pages/      # Dashboard & Login
│       │   └── api/        # Client-side API logic
│       └── vite.config.js
├── .gitignore
├── .env.example
└── README.md
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
