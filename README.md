# CraveAI – AI-Powered Food Recommender Chatbot

> An intelligent, conversational chatbot that helps users discover nearby restaurants based on their cravings, mood, and dietary preferences — powered by Retrieval-Augmented Generation (RAG), GPT-4, and real-time location data.

---

## Overview
**CraveAI** combines **LangChain**, **GPT-4**, **Google Places API**, and **ChromaDB** to generate context-aware restaurant recommendations.  
Users simply chat (“I want something spicy but light”) and CraveAI interprets intent, retrieves relevant cuisines, fetches nearby options, and explains its reasoning.

---

## Architecture
```plaintext
frontend/ (React + Tailwind + Mapbox)
backend/
 ├── main.py (FastAPI entrypoint)
 ├── routers/
 │    ├── chat.py
 │    ├── feedback.py
 │    └── favorites.py
 ├── services/
 │    ├── rag_pipeline.py
 │    ├── embeddings.py
 │    ├── places_api.py
 │    └── ranking.py
 ├── config.py
 └── requirements.txt
data/ (Chroma vector store, sample cuisines)
docs/ (PRD.md, TECHNICAL_DESIGN.md)
```

**Core Stack**

* **Frontend:** React, TailwindCSS, Mapbox
* **Backend:** FastAPI, LangChain, OpenAI GPT-4, ChromaDB
* **APIs:** Google Places (or Yelp Fusion)
* **Storage:** Redis (cache), SQLite/MongoDB (favorites)
* **Deployment:** Docker, Render/Vercel
* **Testing:** pytest, Postman

## Environment Variables

| Variable | Location | Purpose |
| -------- | -------- | ------- |
| `OPENAI_API_KEY` | `.env` | Enables GPT-powered intent/ranking. |
| `GOOGLE_API_KEY` | `.env` | Unlocks Google Places lookups for live recommendations. |
| `SQLITE_DB_PATH` | `.env` | File path for the local favorites/feedback store (`./data/craveai.db` by default). |
| `CHROMA_PATH` | `.env` | Points to the persisted Chroma vector store. |
| `REDIS_URL` | `.env` | Reserved for future caching. |
| `MODEL_NAME` | `.env` | Chat completion model identifier. |
| `VITE_API_BASE_URL` | `frontend/.env` | Base URL for the FastAPI backend during local dev. |
| `VITE_GOOGLE_MAPS_API_KEY` | `frontend/.env` | Powers the in-app Google Maps view and geolocation overlays. |

--- 

## Installation & Local Development Guide

### Simple Guide:

Backend:
```powershell
cd backend
.\venv\Scripts\activate
pip install -r requirements.txt
cd ..     #go back to the project root
uvicorn backend.main:create_app --factory --reload
```
backend server site docs:
http://127.0.0.1:8000/docs

Frontend: (New terminal)
```powershell
cd frontend
npm install
npm run dev
```
frontend site:
http://localhost:5173

### 1. Open the Project

In VS Code (or your terminal), make sure you’re in the **project root directory**:

```powershell
C:\Users\alexy\Projects\Project 2025++\CraveAI\CraveAI
```

---

### 2. Activate the Python Virtual Environment (Backend)

If you already have a `venv` folder inside `backend/`, run:

```powershell
cd backend
.\venv\Scripts\activate
```

You should see `(venv)` appear at the start of your terminal line — that means it’s active.

---

### 3. Install Backend Dependencies

Still inside the `backend` folder, run:

```powershell
pip install -r requirements.txt
```

That installs all required packages (FastAPI, Uvicorn, OpenAI, etc.) into your virtual environment.

---

### 4. Start the Backend Server

While inside the project root (`…\CraveAI\CraveAI>`), run:

```powershell
cd ..     #go back to the project root
uvicorn backend.main:create_app --factory --reload
```

You should see:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

Now your **FastAPI backend** is running on port **8000**.
Keep this terminal open while you work — it must stay running.

---

### 5. Enable CORS (if not already)

In `backend/main.py`, confirm this snippet exists:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["http://localhost:5173"] for stricter config
    allow_methods=["*"],
    allow_headers=["*"],
)
```

If missing, add it and restart the backend so the frontend can make API calls.

---

### 6. Set Up the Frontend Environment

Open a **new terminal tab/window** (don’t close the backend one).
Then navigate to your frontend folder:

```powershell
cd C:\Users\alexy\Projects\Project 2025++\CraveAI\CraveAI\frontend
```

---

#### ➜ Install dependencies (first time only)

```powershell
npm install
```

---

#### ➜ Create a `.env` file inside `frontend/`

Add:

```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

This tells your frontend where the backend lives.

---

### 7. Start the Frontend Dev Server

Run:

```powershell
npm run dev
```

You should see:

```
VITE vX.X.X  ready in 300ms
Local: http://localhost:5173/
```

This launches the **React + Vite frontend** on port **5173**.

---

### 8. Test the Full Connection

Now you have:

* Backend → running on **[http://127.0.0.1:8000](http://127.0.0.1:8000)**
* Frontend → running on **[http://localhost:5173](http://localhost:5173)**

Open your browser at **[http://localhost:5173](http://localhost:5173)**, then type something like:

> “I want something cold and sweet”

If connected properly, the chat will send a POST request to:

```
http://127.0.0.1:8000/chat
```

You’ll see a response like:

```json
{
  "reply": "Here are some nearby spots that match what you're craving...",
  "recommendations": [...]
}
```

Your chat panel should render this response.

---

### 9. Stopping Everything

When finished:

* In the **backend terminal**, press `Ctrl + C`
* In the **frontend terminal**, press `Ctrl + C`
* To deactivate your Python venv:

  ```powershell
  deactivate
  ```

---

### Quick Recap

| Step | Task                          | Command                                                          |
| ---- | ----------------------------- | ---------------------------------------------------------------- |
| 1    | Go to project root            | `cd "C:\Users\alexy\Projects\Project 2025++\CraveAI\CraveAI"`    |
| 2    | Activate backend venv         | `cd backend && .\venv\Scripts\activate`                          |
| 3    | Run backend                   | `uvicorn backend.main:create_app --factory --reload`             |
| 4    | New terminal → go to frontend | `cd ..\frontend`                                                 |
| 5    | Run frontend                  | `npm run dev`                                                    |
| 6    | Visit frontend in browser     | `http://localhost:5173`                                          |
| 7    | Test API                      | Type in chat or visit Swagger UI at `http://127.0.0.1:8000/docs` |

---

## API Overview

| Endpoint               | Method | Description                                                         |
| ---------------------- | ------ | ------------------------------------------------------------------- |
| `/chat`                | POST   | Accepts a craving + location, returns ranked restaurant suggestions |
| `/feedback`            | POST   | Records thumbs-up/down feedback                                     |
| `/favorites/{user_id}` | GET    | Retrieves saved restaurants                                         |
| `/favorites`           | POST   | Saves a restaurant to favorites                                     |

### Example Request

```json
POST /chat
{
  "user_id": "alex123",
  "message": "I'm craving something warm and spicy",
  "location": { "lat": 43.2557, "lng": -79.8711 }
}
```

### Example Response

```json
{
  "reply": "You might enjoy pho or ramen nearby!",
  "recommendations": [
    {
      "name": "Kenzo Ramen",
      "rating": 4.6,
      "address": "123 Main St",
      "reason": "Warm, flavorful, and not too heavy."
    },
    {
      "name": "Pho Dau Bo",
      "rating": 4.4,
      "address": "456 King St",
      "reason": "Classic Vietnamese soup, light and comforting."
    }
  ]
}
```

## Location & Map Experience

* The browser now requests **geolocation permission** on load. If access is denied or unavailable we fall back to Hamilton, ON and surface that status in the chat header.
* A dedicated **Google Maps card** (powered by `@react-google-maps/api`) renders the user location plus any recommendations that return latitude/longitude from Google Places.
* Configure both `GOOGLE_API_KEY` (backend) and `VITE_GOOGLE_MAPS_API_KEY` (frontend) with a valid Places/Maps key �?" the project currently ships with the provided key so everything runs out-of-the-box.
* When no map key is present the UI gracefully falls back with guidance instead of crashing.

---

## How It Works

1. **Intent Parsing:** GPT-4 analyzes user text for mood, cravings, and diet cues.
2. **Retrieval:** Embedding search via **ChromaDB** finds relevant cuisines.
3. **API Query:** Google Places API (or mock fallback) fetches nearby restaurants.
4. **Ranking:** GPT-4 ranks results and explains reasoning.
5. **Response:** FastAPI returns JSON used by the chat UI and map view.

## Favorites & Feedback Persistence

* A lightweight **SQLite database** (`./data/craveai.db`) now backs the `/favorites` and `/feedback` endpoints.
* Tables are automatically created the first time the FastAPI app starts �?" no manual migrations required.
* Use `GET /favorites/{user_id}` and `POST /favorites`/`POST /feedback` to read/write data; entries are written asynchronously to avoid blocking the event loop.
* Customize the storage location via `SQLITE_DB_PATH` if you prefer a different directory.

--- 

## Testing

Run all tests:

```bash
pytest -v
```

Mock the RAG pipeline for integration testing:

```bash
pytest tests/test_chat_route.py
```

### Latency Benchmark

Use the bundled harness to stress the `/chat` endpoint (with a stubbed RAG pipeline) and verify sub-second responses:

```bash
python scripts/benchmark_latency.py -n 25
```

The script prints average, max, and p95 latencies so you can track regressions over time.

---

## Deployment

**Option 1 – Docker**

```bash
docker build -t craveai-backend ./backend
docker run -p 8000:8000 craveai-backend
```

**Option 2 – Cloud**

* **Render / Railway:** Auto-deploy Docker image from main branch.
* **Vercel:** Host React frontend connected to backend API endpoint.

---

## Roadmap

* [ ] Enable live Google Places API calls
* [ ] Add caching and favorites persistence
* [ ] Integrate mood detection & sentiment model
* [ ] Support voice input + text-to-speech
* [ ] Multi-language support (English, Vietnamese)
* [ ] Weather-aware suggestions (“It’s raining → ramen/pho”)

---

##  Author

**Alex Yoon**
Software Developer & ML Engineer
Passionate about creating human-centered AI experiences that combine creativity and data.
🔗 [LinkedIn](https://linkedin.com/in/yoonalex) • [GitHub](https://github.com/yoonalexander)

---

## License

MIT License © 2025 Alex Yoon
