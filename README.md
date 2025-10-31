# 🍜 CraveAI – AI-Powered Food Recommender Chatbot

> An intelligent, conversational chatbot that helps users discover nearby restaurants based on their cravings, mood, and dietary preferences — powered by Retrieval-Augmented Generation (RAG), GPT-4, and real-time location data.

---

## 🚀 Overview
**CraveAI** combines **LangChain**, **GPT-4**, **Google Places API**, and **ChromaDB** to generate context-aware restaurant recommendations.  
Users simply chat (“I want something spicy but light”) and CraveAI interprets intent, retrieves relevant cuisines, fetches nearby options, and explains its reasoning.

---

## 🧱 Architecture
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
````

**Core Stack**

* **Frontend:** React, TailwindCSS, Mapbox
* **Backend:** FastAPI, LangChain, OpenAI GPT-4, ChromaDB
* **APIs:** Google Places (or Yelp Fusion)
* **Storage:** Redis (cache), SQLite/MongoDB (favorites)
* **Deployment:** Docker, Render/Vercel
* **Testing:** pytest, Postman

---

## ⚙️ Installation

### 1. Clone the Repository

```bash
git clone https://github.com/<your-username>/craveai.git
cd craveai
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
source venv/bin/activate   # on macOS/Linux
venv\Scripts\activate      # on Windows
```

### 3. Install Backend Dependencies

```bash
pip install -r backend/requirements.txt
```

### 4. Set Environment Variables

Create a `.env` file in the project root (or copy from `.env.example`):

```bash
OPENAI_API_KEY=your-openai-api-key
GOOGLE_API_KEY=your-google-api-key
CHROMA_PATH=./data/chroma_db
REDIS_URL=redis://localhost:6379
MODEL_NAME=gpt-4-turbo
```

### 5. Run the Backend

```bash
uvicorn backend.main:create_app --factory --reload
```

### 6. Run the Frontend

```bash
cd frontend
npm install
npm run dev
```

Backend defaults to [http://localhost:8000](http://localhost:8000)
Frontend defaults to [http://localhost:5173](http://localhost:5173)

---

## 💬 API Overview

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

---

## 🧠 How It Works

1. **Intent Parsing:** GPT-4 analyzes user text for mood, cravings, and diet cues.
2. **Retrieval:** Embedding search via **ChromaDB** finds relevant cuisines.
3. **API Query:** Google Places API fetches nearby restaurants.
4. **Ranking:** GPT-4 ranks results with natural explanations.
5. **Response:** FastAPI returns JSON used by the chat UI and map view.

---

## 🧪 Testing

Run all tests:

```bash
pytest -v
```

Mock the RAG pipeline for integration testing:

```bash
pytest tests/test_chat_route.py
```

---

## 🌍 Deployment

**Option 1 – Docker**

```bash
docker build -t craveai-backend ./backend
docker run -p 8000:8000 craveai-backend
```

**Option 2 – Cloud**

* **Render / Railway:** Auto-deploy Docker image from main branch.
* **Vercel:** Host React frontend connected to backend API endpoint.

---

## 📈 Roadmap

* [ ] Enable live Google Places API calls
* [ ] Add caching and favorites persistence
* [ ] Integrate mood detection & sentiment model
* [ ] Support voice input + text-to-speech
* [ ] Multi-language support (English, Vietnamese)
* [ ] Weather-aware suggestions (“It’s raining → ramen/pho”)

---

## 👨‍💻 Author

**Alex Yoon**
Application Developer & AI Engineer
Passionate about creating human-centered AI experiences that combine creativity and data.
🔗 [LinkedIn](https://linkedin.com/in/yoonalexander) • [GitHub](https://github.com/yoonalexander)

---

## 🪪 License

MIT License © 2025 Alex Yoon
