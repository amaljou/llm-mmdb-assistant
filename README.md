# LLM-based Natural Language to AQL Query Generation for ArangoDB

## Overview

This project develops an intelligent assistant capable of transforming natural language questions into ArangoDB AQL queries using Large Language Models (LLMs). The system leverages Retrieval-Augmented Generation (RAG) to provide schema-aware query generation, an agent-based validation and correction pipeline, and a privacy filter to protect sensitive data.

## Problem Statement

Modern multi-model databases like ArangoDB offer powerful querying capabilities through AQL, but writing correct queries requires deep knowledge of the database schema and query syntax. Natural language interfaces bridge this gap by allowing users to interact with databases using everyday language. However, generating correct queries from natural language remains challenging due to schema complexity, syntactic requirements, and the need for domain understanding.

## Objectives

- **Schema Understanding**: Automatically extract and index database schema information for context-aware generation
- **Natural Language Interpretation**: Convert user questions into structured AQL queries using LLMs
- **RAG-enhanced Generation**: Retrieve relevant schema elements and example queries to improve generation quality
- **Agent Validation**: Implement a multi-step validation and correction pipeline using schema-guided repair and LLM-based correction
- **Privacy Protection**: Filter queries that access sensitive fields (latitude, longitude, full address, review text)
- **Experimental Evaluation**: Benchmark multiple LLM approaches (Mistral, DeepSeek-Coder) with comprehensive metrics

## Technologies

| Category | Technologies |
|----------|-------------|
| Language | Python |
| Database | ArangoDB, AQL |
| LLM Models | Mistral, DeepSeek-Coder (6.7B) |
| RAG Framework | ChromaDB, Sentence Transformers |
| LangChain | langchain-core, langchain-chroma, langchain-huggingface |
| Web App | Streamlit |
| LLM Server | Ollama |
| Visualization | Matplotlib |

## Project Structure

```
LLM_Yelp_Project/
├── README.md
├── REPORT.md
├── requirements.txt
├── .gitignore
├── app.py                          # Streamlit web application
├── notebooks/
│   ├── 01_arangodb_setup.ipynb
│   ├── 02_dataset_exploration.ipynb
│   ├── 03_reference_aql_queries.ipynb
│   ├── 04_llm_prompting_baseline.ipynb
│   ├── 05_rag_schema_aware_generation.ipynb
│   └── 06_evaluation_analysis.ipynb
├── src/
│   ├── db_connector.py             # ArangoDB connection
│   ├── evaluator.py                # Query execution & comparison
│   ├── privacy_filter.py           # Sensitive field detection
│   ├── prompt_builder.py           # LLM prompt construction
│   ├── query_executor.py           # Safe query execution
│   ├── query_generator.py          # LLM generation & agent pipeline
│   ├── query_validator.py          # Static schema validation
│   └── schema_profiler.py          # Schema extraction from ArangoDB
├── arangodb/
│   └── schema_description.json     # Database schema description
├── results/
│   ├── generated_queries.csv
│   ├── execution_results.csv
│   ├── metrics.csv
│   ├── agent_mistral_results.csv
│   ├── agent_deepseek_results.csv
│   ├── agent_execution_results.csv
│   ├── agent_mistral_metrics.csv
│   ├── agent_models_comparison.csv
│   ├── direct_vs_agent_final.csv
│   └── figures/
│       ├── error_matrix.png
│       └── model_rates_comparison.png
└── data/
    └── benchmark/
        └── yelp_benchmark.json
```

## Project Notebooks

### 01_arangodb_setup.ipynb

ArangoDB configuration and database initialization. Establishes the connection to the YelpDB database, verifies the graph structure (YelpGraph), and ensures all document and edge collections are accessible.

### 02_dataset_exploration.ipynb

Yelp dataset analysis and exploration. Examines the structure of businesses, users, reviews, tips, categories, checkins, and neighborhoods collections. Provides statistics and distributions to understand the data landscape.

### 03_reference_aql_queries.ipynb

Reference AQL query construction and benchmark preparation. Defines the 128 gold-standard AQL queries covering various query types: simple filters, graph traversals, aggregations, multi-hop joins, and complex combinations.

### 04_llm_prompting_baseline.ipynb

Baseline evaluation of LLM prompting strategies. Compares three approaches:
- **Direct Prompting**: Question only, no schema context
- **Schema Prompting**: Full schema description included
- **Few-shot Prompting**: Schema + retrieved examples

### 05_rag_schema_aware_generation.ipynb

RAG pipeline implementation for schema-aware query generation. Uses Sentence Transformers embeddings with ChromaDB to retrieve relevant schema elements and example queries. Implements context expansion and filtered retrieval.

### 06_evaluation_analysis.ipynb

Comprehensive evaluation and analysis. Computes metrics (validation rate, execution rate, functional accuracy), compares models (Mistral vs DeepSeek-Coder), and visualizes results with error matrices and performance charts.

## Experimental Results

### Result Files

| File | Description |
|------|-------------|
| `generated_queries.csv` | AQL queries generated by LLM models (Mistral, DeepSeek-Coder) |
| `execution_results.csv` | Execution results of generated queries on ArangoDB |
| `metrics.csv` | Global evaluation metrics per model |
| `agent_mistral_results.csv` | Results obtained using the Mistral agent pipeline |
| `agent_deepseek_results.csv` | Results obtained using the DeepSeek-Coder agent pipeline |
| `agent_execution_results.csv` | Execution results after agent validation and correction |
| `agent_mistral_metrics.csv` | Detailed metrics for the Mistral agent |
| `agent_models_comparison.csv` | Agent-level comparison between LLM models |
| `direct_vs_agent_final.csv` | Comparison between direct RAG generation and agent-augmented generation |

### Evaluation Metrics

| Metric | Description |
|--------|-------------|
| Validation Rate | Percentage of generated queries passing static schema validation |
| Execution Rate | Percentage of queries successfully executed on ArangoDB |
| Functional Accuracy | Percentage of queries returning results matching the gold standard |
| Correction Rate | Percentage of initially invalid queries corrected by the agent |
| Generation Time | Average time for LLM to produce a query |

### Approaches Evaluated

| Approach | Description |
|----------|-------------|
| **Direct Prompting** | Baseline: question only, no schema context |
| **Schema Prompting** | Full schema description provided in the prompt |
| **Few-shot Prompting** | Schema + similar question-AQL examples |
| **RAG** | Dynamic retrieval of relevant schema and examples using embeddings |
| **RAG + Agent** | RAG generation with agent-based validation, correction, and execution feedback |

### Key Results

- **DeepSeek-Coder** achieves 50.0% functional accuracy with direct RAG, compared to 32.81% for Mistral
- The **agent pipeline** improves validation rates: Mistral increases from 85.94% to 91.41%
- **Schema-guided repair** resolves attribute case errors and structural issues deterministically
- **Execution-based correction** catches runtime errors that static validation misses

## Installation

```bash
# Clone the repository
git clone https://github.com/username/LLM_Yelp_Project.git
cd LLM_Yelp_Project

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Prerequisites

1. **ArangoDB** running on `localhost:8529` with the YelpDB database loaded
2. **Ollama** running with models `mistral:latest` and `deepseek-coder:6.7b`

### Run the Streamlit App

```bash
streamlit run app.py
```

### Run Notebooks

```bash
jupyter notebook notebooks/
```

Run notebooks in order (01 through 06) to reproduce the full experimental pipeline.

## System Architecture

```
User Question
      │
      ▼
┌─────────────┐
│  RAG Engine │──► Schema Retrieval (ChromaDB)
│             │──► Example Retrieval (ChromaDB)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  LLM Engine │──► Mistral / DeepSeek-Coder (Ollama)
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│ Query Validator   │──► Static schema checks
│ Schema Repair     │──► Deterministic corrections
│ LLM Correction    │──► Dynamic error fixing
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Privacy Filter    │──► Sensitive field detection
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Query Executor    │──► ArangoDB execution
│ Execution Fix     │──► Runtime error correction
└──────┬───────────┘
       │
       ▼
   Results
```

## Citation

If you use this project in your research, please cite:

```
LLM-based Natural Language to AQL Query Generation for ArangoDB
Master's/PFE Project — 2026
```

## License

This project is for academic/research purposes.
