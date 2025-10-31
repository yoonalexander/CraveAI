# CraveAI – Technical Design Document
**Author:** Alex Yoon  
**Date:** October 2025  
**Version:** 1.0  

---

## Overview
CraveAI is an AI-powered conversational system that recommends nearby restaurants based on user cravings, mood, and dietary preferences.  
This document provides the **technical architecture**, **data flow**, **API specifications**, and **module breakdown** for the system implementation.

---

## System Architecture

### High-Level Components
| Component | Description | Technology |
|------------|--------------|-------------|
| **Frontend (Client)** | User interface for chatting, maps, filters, and results. | React, TailwindCSS, Mapbox |
| **Backend (API Server)** | Handles requests, orchestrates RAG pipeline, calls APIs. | FastAPI (Python) |
| **RAG Pipeline** | Retrieves cuisine embeddings, queries LLM with context. | LangChain, GPT-4 |
| **Vector Database** | Stores cuisine embeddings for semantic retrieval. | ChromaDB / FAISS |
| **External APIs** | Provides restaurant data by location and cuisine. | Google Places API / Yelp Fusion |
| **Caching & Storage** | Improves performance and stores session/favorites. | Redis (cache), SQLite / MongoDB (data) |

---

## Data Flow

### Step-by-Step Flow
1. **User Input (Frontend):**  
   User types or speaks a craving, e.g. “I want something spicy but not heavy.”

2. **Intent Parsing (Backend):**  
   LLM or rule-based parser identifies:
   - Mood: spicy, light  
   - Cuisine category: Asian, soup  
   - Dietary preferences: none specified

3. **RAG Retrieval:**  
   - System retrieves relevant cuisine embeddings (`pho`, `ramen`, `tom yum`).  
   - Uses cosine similarity search from ChromaDB.

4. **External API Query:**  
   - FastAPI calls Google Places API with cuisine names + coordinates.  
   - Retrieves nearby restaurants with details (name, rating, price, distance).

5. **LLM Ranking & Explanation:**  
   - LangChain composes a prompt including:
     - user query  
     - retrieved cuisines  
     - restaurant results  
   - GPT-4 ranks and explains top recommendations.

6. **Response Generation (Frontend):**  
   - Chat message + list of recommendations  
   - Optional map visualization (Mapbox markers)

7. **Feedback & Storage:**  
   - User can like/dislike → updates learning weights or stores preferences.

---

## Architecture Diagram (ASCII)

```plaintext
        ┌────────────────────────┐
        │        Frontend         │
        │ React + Mapbox Chat UI │
        └───────────┬────────────┘
                    │
                    ▼
        ┌────────────────────────┐
        │       FastAPI API       │
        │ Routes, Auth, Orchestration │
        └───────────┬────────────┘
                    │
        ┌────────────────────────┐
        │    RAG Orchestrator     │
        │  LangChain + GPT-4       │
        └───────────┬────────────┘
          │          │          │
          ▼          ▼          ▼
 ┌────────────┐  ┌────────────┐ ┌────────────┐
 │ Vector DB  │  │ Places API │ │ Cache/DB   │
 │ Chroma/FAISS│ │ Google/Yelp│ │ Redis/SQLite│
 └────────────┘  └────────────┘ └────────────┘
````

---

## Backend Design

### Directory Structure

```plaintext
backend/
├── main.py               # FastAPI app entry
├── routers/
│   ├── chat.py           # POST /chat
│   ├── location.py       # GET /location
│   ├── favorites.py      # GET/POST favorites
├── services/
│   ├── rag_pipeline.py   # RAG orchestration logic
│   ├── embeddings.py     # Cuisine embedding & retrieval
│   ├── places_api.py     # External API wrapper
│   ├── ranking.py        # GPT-based ranking & explanation
├── models/
│   ├── user.py
│   ├── restaurant.py
│   └── message.py
├── utils/
│   ├── cache.py
│   ├── config.py
│   └── logger.py
└── requirements.txt
```

---

## API Endpoints

### 1. `POST /chat`

**Description:** Handles chat input, runs RAG pipeline, returns recommendations.

#### Request

```json
{
  "user_id": "abc123",
  "message": "I want something spicy but light",
  "location": {
    "lat": 43.2557,
    "lng": -79.8711
  }
}
```

#### Response

```json
{
  "reply": "How about pho or ramen nearby?",
  "recommendations": [
    {
      "name": "Kenzo Ramen",
      "rating": 4.6,
      "address": "123 Main St",
      "distance_km": 1.2,
      "reason": "Warm, flavorful, not too heavy."
    },
    {
      "name": "Pho Dau Bo",
      "rating": 4.4,
      "address": "456 King St",
      "distance_km": 2.0,
      "reason": "Classic Vietnamese soup, light broth."
    }
  ]
}
```

---

### 2. `GET /location`

**Description:** Returns geolocation based on IP (if browser permission not granted).
**Response:**

```json
{ "lat": 43.25, "lng": -79.87, "city": "Hamilton" }
```

---

### 3. `GET /favorites/{user_id}`

**Description:** Fetch saved favorite restaurants.
**Response:**

```json
{ "favorites": [ { "name": "Kenzo Ramen", "rating": 4.6 } ] }
```

---

### 4. `POST /feedback`

**Description:** Collects thumbs-up/down feedback to refine ranking.
**Request:**

```json
{ "user_id": "abc123", "restaurant": "Kenzo Ramen", "liked": true }
```

---

## Core Modules

### `rag_pipeline.py`

Handles:

* Parsing user input (mood, craving, diet)
* Retrieving embeddings (Chroma)
* Fetching restaurant data (Places API)
* Generating ranked responses (GPT-4)

```python
def generate_recommendations(user_query, location):
    intent = parse_intent(user_query)
    cuisines = retrieve_similar_cuisines(intent)
    places = fetch_places(cuisines, location)
    ranked = rank_with_llm(user_query, cuisines, places)
    return ranked
```

---

### `embeddings.py`

* Uses `sentence-transformers/all-MiniLM-L6-v2` or `OpenAI Embeddings`
* Stores 200+ cuisine vectors in ChromaDB.
* Supports cosine similarity search for `top_k=5`.

---

### `places_api.py`

Handles all communication with Google Places API.

* Endpoint: `https://maps.googleapis.com/maps/api/place/nearbysearch/json`
* Parameters: `location`, `radius`, `type=restaurant`, `keyword=<cuisine>`

---

### `ranking.py`

Uses GPT-4 prompt templating to rank and reason through results.

```python
PROMPT_TEMPLATE = """
You are a food recommendation assistant.
User craving: {query}
Candidate restaurants: {restaurants}
Rank the top 3 and explain why they fit best.
"""
```

---

## Environment Variables (`.env`)

```
OPENAI_API_KEY=sk-xxxx
GOOGLE_API_KEY=AIza....
CHROMA_PATH=./data/chroma_db
REDIS_URL=redis://localhost:6379
```

---

## Performance Considerations

* **Async I/O** for all API calls (`httpx`, `asyncio`)
* **Caching**: Cache previous Places API responses in Redis
* **Batch embedding retrieval** to reduce latency
* **LLM call optimization**: Context window limited to 1k tokens

---

## Testing Plan

| Type        | Tool                    | Description                                    |
| ----------- | ----------------------- | ---------------------------------------------- |
| Unit Tests  | `pytest`                | Test parsing, retrieval, and ranking functions |
| Integration | `pytest-asyncio`        | Test full pipeline with mock APIs              |
| API Tests   | `Postman` / `Pytest`    | Validate endpoints and response times          |
| UI Tests    | `React Testing Library` | Simulate chat and map rendering                |

---

## Deployment

* **Backend:** Dockerized FastAPI on Render or AWS EC2
* **Frontend:** React app deployed on Vercel
* **Database:** ChromaDB (local) or managed vector DB like Pinecone
* **CI/CD:** GitHub Actions – run tests & redeploy on main branch push

---

## Future Enhancements

* Fine-tune local model for craving intent classification
* Add personalization layer with user embeddings
* Expand cuisine dataset dynamically from API feedback
* Add voice input and TTS responses
* Support offline cache for mobile users