# LangGraph Support-Ticket Agent & Local Verification Guide

This repository contains a production-style LangGraph support-ticket agent designed to classify intent, route workflows, evaluate tool outputs via an LLM-as-judge loop, require human-in-the-loop (HITL) approval for risky actions, and persist state history using SQLite.

---

## 🛠️ Environment & Setup Instructions

### 1. Create and Activate Virtual Environment (Windows)
Create the virtual environment using Python 3.12:
```bash
py -3.12 -m venv .venv
```

Activate the environment based on your shell:
- **PowerShell**:
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
- **Command Prompt (CMD)**:
  ```cmd
  .\.venv\Scripts\activate.bat
  ```

### 2. Install Project Dependencies
Install all developer and checkpointer dependencies:
```bash
.\.venv\Scripts\pip install -e .[dev,sqlite,google]
```

### 3. Setup Environment Variables (`.env`)
Create your `.env` file from the example:
```bash
cp .env.example .env
```
Open `.env` and fill in:
- `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY` for LLM calls.
- `LANGCHAIN_API_KEY` for LangSmith tracing (optional, recommended).
- Set `CHECKPOINTER=sqlite` to enable SQLite database persistence.

---

## 🧪 Testing & Validation Guide (Pre-push Check)

Always run the following verification steps locally before committing your code and pushing to Git:

### 1. Run Unit Tests
Verifies state transitions, routing logic, and graph execution (including LLM-mocking):
```bash
.\.venv\Scripts\pytest
```

### 2. Run Scenario Simulations
Runs 7 test scenarios (simple query, tool query, vague query, risky refund, transient error, delete account, and dead letter fallback):
```bash
.\.venv\Scripts\python -m langgraph_agent_lab.cli run-scenarios --config configs/lab.yaml --output outputs/metrics.json
```

### 3. Validate Metrics Output
Confirms that the output `metrics.json` is schema-compliant and matches expected routes:
```bash
.\.venv\Scripts\python -m langgraph_agent_lab.cli validate-metrics --metrics outputs/metrics.json
```

### 4. Check Linting Rules (Ruff)
Checks Python style guidelines and fixes autofixable formatting issues:
```bash
# Check code style
.\.venv\Scripts\ruff check src

# Auto-fix linting issues
.\.venv\Scripts\ruff check src --fix
```

### 5. Check Strict Type Safety (Mypy)
Ensures strict type-hints compile correctly without warnings:
```bash
.\.venv\Scripts\mypy src
```

---

## 🚨 Git Pre-Push Checklist

Before you run `git push`, double-check the following items to avoid broken builds or credential leaks:

- [ ] **No Secret Leaks**: Verify that `.env` is NOT tracked by Git (`.gitignore` must contain `.env`). Do not hardcode API keys in `nodes.py` or `llm.py`.
- [ ] **All Tests Pass**: `.\.venv\Scripts\pytest` must run successfully without errors.
- [ ] **Lint and Types Clear**: Running `ruff check src` and `mypy src` must print success outputs with zero errors.
- [ ] **100% Success Rate**: Scenario runs must achieve `success_rate=100.00%` when validated locally.
- [ ] **Report Written**: The dynamic report file `reports/lab_report.md` must be fully generated and match your architecture descriptions.
