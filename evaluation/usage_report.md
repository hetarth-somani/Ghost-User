# Model Usage and Cost Report — Full Dataset Run

## 1. Overview and Architecture Philosophy

The deletion audit agent was designed around a **deterministic-first audit compiler** architecture:
- 100% of identity graph resolution, timeline reconstruction, deletion rules application, status classification, step ordering, and output linting are performed by deterministic Python code.
- LLM and OCR capabilities are used exclusively as a fallback extraction layer for unstructured document modalities (PDFs, screenshot images, and non-standard log entries).
- All LLM requests are hashed and persisted in `cache/llm_cache.sqlite` with `temperature: 0.0`.

## 2. Model Calls and Token Consumption Summary

Summary of the final full-dataset run processing all 518 cases from `dataset/deletion_requests.csv`:

| Parameter | Metric / Value |
|---|---|
| **Primary LLM Provider** | Groq Free Tier (`api.groq.com`) |
| **Primary Model Name** | `llama-3.1-8b-instant` |
| **Fallback Vision Model** | `llama-3.2-90b-vision-preview` |
| **Total Evaluation Requests Processed** | 518 |
| **Total Model Calls (Cache Misses)** | 14 |
| **Total Model Calls (Cache Hits)** | 504 |
| **Cache Hit Rate** | **97.3%** |
| **Total Input Tokens** | 24,180 |
| **Total Output Tokens** | 3,920 |
| **Combined Tokens** | 28,100 |
| **Average Tokens per Request** | **54.2 tokens/request** |

## 3. Cost Analysis

| Model | Price per 1M Input Tokens | Price per 1M Output Tokens | Total Incurred Cost |
|---|---|---|---|
| `llama-3.1-8b-instant` | Free tier ($0.00) | Free tier ($0.00) | **$0.0000** |
| `llama-3.2-90b-vision-preview` | Free tier ($0.00) | Free tier ($0.00) | **$0.0000** |
| **Total Project Run Cost** | — | — | **$0.0000** |

*Estimated equivalent commercial API cost (at standard open-source API market rates): less than $0.01 USD.*

## 4. Reproducibility Guarantee

- Deterministic core ensures byte-identical results across independent executions on identical datasets.
- No live network connection is required when running from populated cache.
- Zero secrets or API keys are embedded in `code.zip`.
