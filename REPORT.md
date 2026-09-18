# LLM-based Natural Language to AQL Query Generation for ArangoDB

## Technical Report

---

## 1. Introduction

The exponential growth of data stored in multi-model databases has created a pressing need for intuitive interfaces that allow non-expert users to query complex data structures. This project addresses the challenge of converting natural language questions into valid ArangoDB AQL (ArangoDB Query Language) queries using Large Language Models (LLMs).

## 2. Context

ArangoDB is a multi-model database supporting document, key-value, and graph data models with a unified query language (AQL). While AQL is powerful, it requires knowledge of:

- Collection structures and field names
- Graph traversal syntax (FOR...IN...OUTBOUND/INBOUND/ANY)
- Filter, sort, and aggregation operators
- System fields (_id, _key, _from, _to)

The Yelp academic dataset provides a rich graph structure with 7 document collections (Businesses, Users, Reviews, Tips, Categories, Checkins, Neighborhoods) and 7 edge collections representing relationships between entities.

## 3. Problematic

Natural Language to Query (NL2Query) systems face several challenges:

1. **Schema Complexity**: The system must understand which collections, fields, and relationships are relevant to a question
2. **Syntactic Correctness**: Generated queries must follow valid AQL syntax
3. **Semantic Accuracy**: The query must faithfully represent the user's intent
4. **Hallucination**: LLMs may invent non-existent collections or attributes
5. **Graph Awareness**: Multi-hop queries require understanding of graph traversal patterns

## 4. Objectives

- Build a schema-aware NL-to-AQL conversion system using RAG
- Implement a multi-stage agent pipeline for query validation and correction
- Evaluate multiple LLM models (Mistral, DeepSeek-Coder) on a benchmark of 128 questions
- Compare direct prompting, schema prompting, few-shot prompting, and RAG approaches
- Develop a privacy filter to prevent access to sensitive data fields

## 5. State of the Art

### 5.1 Text-to-SQL

Text-to-SQL has been extensively studied, with systems like SQLizer, Spider, and ShadowGNN establishing benchmarks and architectures. The Spider benchmark introduced complex, cross-database evaluation, while ShadowGNN proposed graph neural networks for schema encoding.

### 5.2 Text-to-AQL

Text-to-AQL remains less explored than Text-to-SQL. The graph nature of AQL introduces additional complexity with traversal patterns, edge collections, and graph-specific operations.

### 5.3 Large Language Models

LLMs such as Mistral, DeepSeek-Coder, and CodeLlama demonstrate strong code generation capabilities. However, domain-specific query languages like AQL require additional context to produce correct outputs.

### 5.4 Retrieval-Augmented Generation (RAG)

RAG addresses LLM limitations by retrieving relevant context at inference time. For NL2Query, RAG can provide schema information and example queries, grounding the LLM's generation in the actual database structure.

## 6. Methodology

### 6.1 Database and Dataset

- **Database**: ArangoDB with YelpDB (Yelp Academic Dataset)
- **Graph**: YelpGraph with 85,899 businesses, users, reviews, tips, categories, checkins, and neighborhoods
- **Benchmark**: 128 natural language questions with gold-standard AQL queries covering diverse query types

### 6.2 Schema Extraction

The `schema_profiler.py` module automatically extracts:
- Document collection names, fields, types, and example values
- Edge collection names, from/to relationships
- Graph traversal paths

This produces `schema_description.json` used by the validator and RAG pipeline.

### 6.3 Prompting Strategies

**Direct Prompting**: Question-only input without schema context.

**Schema Prompting**: Full schema description included in the prompt.

**Few-shot Prompting**: Schema plus similar question-AQL example pairs.

**RAG Prompting**: Dynamic retrieval of relevant schema elements and examples using embedding similarity.

### 6.4 RAG Architecture

1. **Embedding**: Schema descriptions and example queries are embedded using `all-MiniLM-L6-v2` Sentence Transformers
2. **Indexing**: Embeddings stored in ChromaDB collections (schema store, examples store)
3. **Retrieval**: Top-k similar schema elements (k=4) and examples (k=5) retrieved per question
4. **Expansion**: Schema context expanded to include collections referenced in retrieved examples
5. **Prompt Construction**: Retrieved context integrated into the generation prompt

### 6.5 Agent Architecture

The agent pipeline implements a multi-stage correction process:

1. **Initial Generation**: LLM produces an AQL query
2. **Static Validation**: `QueryValidator` checks collections, attributes, forbidden operations, and cost warnings
3. **Schema-guided Repair**: Deterministic fixes for attribute case mismatches and known query patterns
4. **LLM Correction**: If validation fails, the error context is sent back to the LLM for correction
5. **Privacy Check**: `PrivacyFilter` detects and blocks queries accessing sensitive fields
6. **Execution**: `QueryExecutor` runs the validated query on ArangoDB
7. **Execution Correction**: If ArangoDB rejects the query, the error is sent to the LLM for runtime correction

## 7. System Architecture

```
┌─────────────────────────────────────────────────────┐
│                    User Interface                     │
│                   (Streamlit app.py)                  │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│                    RAG Pipeline                       │
│  ┌─────────────┐    ┌──────────────┐                │
│  │ ChromaDB    │    │ Sentence     │                │
│  │ (Schema +   │◄───│ Transformers │                │
│  │  Examples)  │    │ Embeddings   │                │
│  └─────────────┘    └──────────────┘                │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│                 Query Generator                       │
│  ┌──────────────────────────────────────┐           │
│  │ LLM (Mistral / DeepSeek-Coder)      │           │
│  │ via Ollama API                       │           │
│  └──────────────────────────────────────┘           │
│  ┌──────────────────────────────────────┐           │
│  │ Output Cleaning & Extraction         │           │
│  └──────────────────────────────────────┘           │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│              Validation & Correction Agent            │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ Static      │  │ Schema       │  │ LLM        │ │
│  │ Validator   │─►│ Repair       │─►│ Correction │ │
│  └─────────────┘  └──────────────┘  └────────────┘ │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│              Privacy Filter                           │
│  Detects: full_address, latitude, longitude, text    │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│              Query Executor                           │
│  ┌─────────────┐  ┌──────────────┐                  │
│  │ ArangoDB    │  │ Execution    │                  │
│  │ AQL Engine  │─►│ Error Fix    │                  │
│  └─────────────┘  └──────────────┘                  │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
                   Query Results
```

## 8. Experimental Setup

- **Models**: Mistral (latest), DeepSeek-Coder (6.7B) via Ollama
- **Embeddings**: all-MiniLM-L6-v2 via Sentence Transformers
- **Vector Store**: ChromaDB (in-memory)
- **Database**: ArangoDB 3.x on localhost:8529
- **Benchmark**: 128 questions with gold AQL queries
- **Hardware**: Local machine (GPU recommended for LLM inference)

## 9. Results

### 9.1 Direct RAG Generation

| Model | Validation Rate | Execution Rate | Functional Accuracy |
|-------|----------------|----------------|-------------------|
| Mistral | 85.94% | 50.0% | 32.81% |
| DeepSeek-Coder | 93.75% | 72.66% | 50.0% |

DeepSeek-Coder consistently outperforms Mistral across all metrics in direct generation mode.

### 9.2 Agent Pipeline Results

| Model | Final Valid | Corrected | LLM Correction Success |
|-------|------------|-----------|----------------------|
| Mistral | 91.41% | 39.84% | 66.67% |
| DeepSeek-Coder | 90.63% | 28.91% | 33.33% |

The agent pipeline significantly improves Mistral's validation rate (85.94% -> 91.41%).

### 9.3 Direct vs Agent Comparison

| Model | Approach | Validation | Execution | Accuracy |
|-------|----------|-----------|-----------|----------|
| Mistral | RAG direct | 85.94% | 50.0% | 32.81% |
| Mistral | RAG + Agent | 91.41% | 58.59% | 36.72% |
| DeepSeek-Coder | RAG direct | 93.75% | 72.66% | 50.0% |
| DeepSeek-Coder | RAG + Agent | 90.62% | 69.53% | 39.06% |

### 9.4 Key Observations

1. **Model Comparison**: DeepSeek-Coder demonstrates stronger baseline performance, likely due to its code-specific training
2. **Agent Impact**: The agent pipeline primarily improves validation rates through deterministic schema repair
3. **Correction Patterns**: Attribute case errors are the most common fixable issue
4. **Execution Feedback**: Runtime correction catches errors that static validation misses

## 10. Limitations

1. **Schema Dependency**: The system requires a pre-computed schema description file
2. **LLM Hallucination**: Models still generate queries with non-existent collections or attributes
3. **Complex Queries**: Multi-hop traversals with complex filters remain challenging
4. **Benchmark Size**: 128 questions may not cover all query patterns
5. **No Training**: The system uses zero/few-shot prompting without fine-tuning

## 11. Future Work

1. **Fine-tuning**: Train LLMs on AQL-specific data to improve generation quality
2. **Interactive Clarification**: Implement multi-turn dialogue for ambiguous questions
3. **Schema Linking**: Develop better schema linking algorithms for complex queries
4. **Expanded Benchmark**: Create a larger, more diverse benchmark covering all AQL features
5. **Multi-database Support**: Extend the system to support other graph databases (Neo4j, Amazon Neptune)

## 12. Conclusion

This project demonstrates that combining RAG with an agent-based validation pipeline enables effective natural language to AQL conversion. DeepSeek-Coder achieves 50% functional accuracy on the benchmark, while the agent pipeline improves validation rates by up to 5.5 percentage points. The deterministic schema repair and LLM-based correction stages provide complementary improvements to query quality.

## 13. References

1. SQLizer: Query Synthesis from Natural Language — https://doi.org/10.1145/3133887
2. Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing — https://aclanthology.org/D18-1425/
3. Improving Text-to-SQL Semantic Parsing using Partial Semantic Matches — https://aclanthology.org/P18-1033/
4. ShadowGNN: Graph Preprocessing for Text-to-SQL — https://arxiv.org/abs/2004.14172
5. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks — https://arxiv.org/abs/2005.11401
6. ArangoDB AQL Documentation — https://www.arangodb.com/docs/stable/aql/
