# CraveAI – AI-Powered Food Recommender Chatbot
> Historical planning document. Its Chroma/FAISS and LangChain sections were
> never implemented and are not the current architecture. See
> [technical_design.md](technical_design.md) for the evidence-grounded engine.

**Author:** Alex Yoon  
**Date:** October 2025  
**Version:** 1.0  

---

## Overview
**CraveAI** is a conversational AI chatbot that recommends restaurants based on a user’s cravings, mood, and dietary preferences, using their current **location**.

The system uses a **Retrieval-Augmented Generation (RAG)** approach, combining LLM-based reasoning with real-time restaurant data from the **Google Places API** (or Yelp Fusion API).  
Users can speak naturally (“I want something cozy and spicy”) and receive personalized, location-aware recommendations.

---

## Goals and Objectives

### Primary Goals
- Enable users to **discover restaurants** that match their cravings and mood.  
- Use **natural language understanding** to interpret vague or emotional input.  
- Integrate **location-based search** for relevant nearby options.  
- Provide **clear explanations** and **alternative suggestions**.

### Secondary Goals
- Support **filters** (distance, price, cuisine, diet).  
- Include a **“Spin Again”** feature for fun random suggestions.  
- Deliver a **fast, intuitive chat interface** on both web and mobile.  
- Optimize for **low latency (<2s)**.

---

## Key Features and Requirements

| Feature | Description | Priority |
|----------|--------------|----------|
| Conversational Interface | Natural chat interface for cravings & moods | Must Have |
| Location Detection | Auto or manual location input | Must Have |
| RAG-Based Reasoning | Retrieve similar cuisines & rank via GPT-4 | Must Have |
| Restaurant Search API | Integrate Google Places / Yelp for results | Must Have |
| Mood-to-Food Mapping | Predefined mood → cuisine logic | Should Have |
| Map View | Interactive map showing recommendations | Should Have |
| Favorites / History | Bookmark or re-visit past suggestions | Could Have |
| Feedback Loop | “Did you like that?” for learning | Could Have |
| Spin Again | Random, fun re-roll of suggestions | Could Have |

---

## User Stories

| Role | Story | Acceptance Criteria |
|------|--------|---------------------|
| User | I want to describe my craving naturally so CraveAI can recommend places nearby. | System interprets phrases like “spicy but light” and returns 3–5 relevant options. |
| User | I want CraveAI to know my location so results are local. | User allows browser location or types city name. |
| User | I want to filter by price or cuisine type. | Filters shown below chat or in settings. |
| User | I want to see results on a map. | Map dynamically displays restaurant pins. |
| User | I want a “spin again” button. | A new set of randomized results appears. |

---

## System Architecture

### Frontend
- **React** + **TailwindCSS**
- Chat UI with messages and filters
- Map view (Mapbox / Google Maps)
- Location access via browser API

### Backend
- **FastAPI (Python)** for REST endpoints
- **LangChain** for RAG orchestration
- **GPT-4 (OpenAI API)** for LLM reasoning
- **ChromaDB / FAISS** for cuisine embeddings
- **Google Places API** for restaurant data
- Optional: **Redis** caching

### Workflow
1. User sends craving →  
2. LLM parses intent (mood, craving, diet) →  
3. Retriever fetches cuisine embeddings (e.g. ramen, pho) →  
4. Google Places API fetches nearby spots →  
5. GPT ranks & explains recommendations →  
6. Chat and map update with results.

---

## Success Metrics

| Metric | Target |
|---------|---------|
| Response latency | < 2.0 seconds |
| Recommendation relevance | ≥ 80% (based on thumbs-up feedback) |
| User retention | ≥ 50% returning users |
| API uptime | ≥ 99% |

---

## Tech Stack

- **Frontend:** React, TailwindCSS, Mapbox  
- **Backend:** FastAPI, LangChain, OpenAI API, Google Places API, ChromaDB  
- **Database:** SQLite or MongoDB (for user history)  
- **Hosting:** Render, Vercel, or Hugging Face Spaces  
- **Version Control:** GitHub  
- **Deployment:** Docker

---

## Non-Functional Requirements

| Category | Requirement |
|-----------|--------------|
| Performance | <2s response time; async API calls |
| Scalability | Modular backend; Dockerized microservices |
| Security | Secure API keys; HTTPS enforced |
| Privacy | Location/chat data not stored without consent |
| Reliability | Cache API responses to reduce rate limits |
| UX | Clean, conversational UI with minimal typing |

---

## Future Enhancements

- Fine-tuned local model for craving intent detection  
- Integration with UberEats / DoorDash APIs  
- Personalized learning from past choices  
- Multi-language support (English, Vietnamese, etc.)  
- Weather-aware suggestions (e.g., “It’s snowing → ramen/pho”)  

---

## Milestones

| Phase | Deliverables | Duration |
|--------|--------------|----------|
| **Phase 1 – MVP** | Chat + location + RAG + API integration | 2 weeks |
| **Phase 2 – Map UI & filters** | Map view, favorites, filters | 2 weeks |
| **Phase 3 – UX polish & deploy** | Animations, caching, hosting | 1 week |

---

## License
MIT License (optional – choose based on repo)

---

## Repository Structure (Recommended)
```plaintext
craveai/
├── backend/
│   ├── main.py
│   ├── routers/
│   ├── utils/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   ├── components/
│   ├── App.jsx
│   └── package.json
├── data/
│   ├── cuisine_embeddings/
│   └── examples/
├── docs/
│   └── PRD.md
└── README.md
