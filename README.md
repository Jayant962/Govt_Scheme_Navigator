# 🇮🇳 AI-Powered Government Scheme Intelligence & Recommendation Platform

> A production-ready full-stack AI project that automatically collects, processes, and recommends Indian government schemes to citizens using **Gemini AI**, **LangChain**, **FAISS**, and **Streamlit**.

---

## 🎯 Project Vision

Most Indians miss out on government schemes they're entitled to because:
- Information is scattered across hundreds of portals
- Eligibility criteria are written in complex language
- No personalized matching exists

**GovtSchemeAI** solves this by:
1. Automatically collecting scheme data from government portals
2. Using AI to extract structured eligibility criteria
3. Running deterministic eligibility scoring for every scheme
4. Generating personalized AI explanations
5. Enabling semantic search via FAISS vector store

---

## 🏗️ Architecture

```
Government Portals
       ↓
Automated Scraper (requests + BeautifulSoup + Playwright)
       ↓
Raw Scheme Data (data/raw/latest.json)
       ↓
AI Eligibility Extractor (Gemini 2.0 Flash + LangChain)
       ↓
Structured Scheme Database (SQLite)
       ↓
Eligibility Engine (deterministic rule-based, 100-point scoring)
       ↓
Ranking Engine (sort + filter top-N)
       ↓
FAISS Vector Store (semantic search)
       ↓
Explanation Chain (LangChain LCEL + Gemini)
       ↓
Streamlit Dashboard
```

---

## 📁 Project Structure

```
govt_scheme_ai/
├── app.py                          # Main Streamlit dashboard
├── update_schemes.py               # Auto-update pipeline (scrape → DB → FAISS)
├── requirements.txt
├── README.md
├── .env                            # API keys (never commit this)
│
├── data_pipeline/
│   ├── scraper.py                  # Web scraper + seed data loader
│   └── extractor.py                # AI eligibility extraction (Gemini + LangChain)
│
├── database/
│   ├── db_manager.py               # SQLite CRUD + analytics + history
│   └── schemes.db                  # Auto-created SQLite database
│
├── modules/
│   ├── eligibility_engine.py       # Deterministic 100-point scoring (no LLM)
│   ├── ranking_engine.py           # Sort + filter recommendations
│   ├── vector_store.py             # FAISS index builder + semantic search
│   └── explanation_chain.py        # LangChain LCEL explanation generator
│
├── data/
│   ├── raw/                        # Raw scraped JSON files
│   └── processed/                  # Processed schemes.json
│
├── vectorstore/                    # FAISS index files
├── reports/                        # Generated PDF reports
└── assets/                         # Static assets
```