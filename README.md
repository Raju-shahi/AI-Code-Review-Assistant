This project is made by myself(Raju shahi) and I don't like to work in a team, but I know to grow in the It industry I should be a team player,

after the first change, I have created a new branch to learn how to merge a local branch to the main pipeline

AI Code Review Assistant

Overview
A FastAPI backend receives GitHub webhook events and stores reviews in memory. A React + Vite + Tailwind dashboard shows the latest reviews.

Backend

- Create and activate a virtual environment
- Install dependencies from backend/requirements.txt
- Start the API server on port 8000

Frontend

- Install dependencies in the frontend folder
- Start the Vite dev server on port 5173

API Notes

- GET /api/health
- GET /api/reviews
- POST /api/reviews
- POST /webhook/github

Required Env (backend/.env)

- OPENAI_API_KEY
- OPENAI_MODEL (default: gpt-4o-mini)
- GITHUB_APP_ID
- GITHUB_PRIVATE_KEY (PEM contents)
- GITHUB_WEBHOOK_SECRET
- DATABASE_URL (default: sqlite+aiosqlite:///./data/reviews.db)

Next Steps

- Add inline GitHub review comments mapped to diff positions
- Add background job queue for higher throughput
- Add review caching and rate limiting
