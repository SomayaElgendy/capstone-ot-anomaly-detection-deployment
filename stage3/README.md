# Stage 3 Deploy

This folder contains the final deployment version of Stage 3 for generating OT/ICS incident response reports from Stage 2 alerts.

This version is deployment-oriented:
- Uses the selected best-performing RAG-based LLM
- Processes alerts one by one
- Uses the updated KDB/VDB retrieval assets
- Uses the real ICS testbed environment configuration
- Generates and evaluates one incident response report per alert

---

# What this folder contains

## Main files

- `run_deployment.py`  
  The main deployment runner.  
  This is the file used to execute Stage 3.

- `hybrid_retriever.py`  
  Performs hybrid retrieval using FAISS dense retrieval, BM25 lexical retrieval, and RRF fusion.  
  It also blends attack-specific retrieval with a general OT/ICS incident-response guidance query.

- `evaluator.py`  
  Evaluates retrieval quality and generated incident-response report quality, including structure, grounding, environment specificity, uncertainty handling, and hallucination-related penalties.

---

# Required data folders

## Environment configuration

- `data/raw/env/configuration.json`  
  Contains the real monitored ICS testbed configuration.  
  It is used to inject environment context into the prompt and to support environment-aware evaluation.

## Knowledge base and vector database

- `data/processed/KDB/chunks_hybrid/chunks.jsonl`  
  Processed retrieval chunks used by the hybrid retriever.

- `data/processed/VDB/faiss.index`  
  FAISS vector index for dense retrieval.

- `data/processed/VDB/build_config.json`  
  Configuration file used to load the embedding model.

- `data/processed/VDB/chunk_metadata.json`  
  Metadata file associated with the vector database build.

Important: `chunks.jsonl`, `faiss.index`, `build_config.json`, and `chunk_metadata.json` should come from the same knowledge-base/vector-database build.

---

# Input alerts

- `outputs/stage2/alerts.json`  
  Stage 2 alerts file used as input for Stage 3 deployment.

Each alert should include:

```json
{
  "predicted_attack": "modify_alarm_settings",
  "classifier_confidence": 0.91,
  "network_anomaly_score": 0.69,
  "process_anomaly_score": 10.75,
  "window_start_time": "2022-01-01T16:56:04.867",
  "window_end_time": "2022-01-01T16:56:14.867",
  "technique_id": "T0838"
}
```

# Output folders
- `outputs/stage3/IR/`  
  Saved incident response reports in Markdown format.

- `outputs/stage3/eval/`  
  Saved evaluation JSON files for each generated report.

---
# What each file does

## 1) `run_deployment.py`
This is the final deployment script.

It:
1. Loads the ICS environment configuration from `data/raw/env/configuration.json`
2. Builds the environment context and asset quick reference
3. Reads the Stage 2 alerts file
4. Processes alerts one by one
5. Builds an attack-aware retrieval query
6. Retrieves relevant OT/ICS chunks using the hybrid retriever
7. Builds the final RAG prompt
8. Sends the prompt to the selected best-performing LLM
9. Saves the generated incident response report
10. Evaluates the generated report and retrieval quality
11. Saves the evaluation output

This file includes multiple internal sections such as:
- Environment context code
- Alert loading
- Prompt construction
- Retrieval wrapper
- LLM execution
- Report and evaluation saving

These section comments are intentional and useful.  
They help explain which older code parts were merged into this final deployment file.

---

## 2) `hybrid_retriever.py`
This file performs the retrieval step.

It:
- Loads processed chunks from `data/processed/KDB/chunks_hybrid/chunks.jsonl`
- Loads the FAISS vector index from `data/processed/VDB/faiss.index`
- Loads the embedding model from `data/processed/VDB/build_config.json`
- Performs dense semantic retrieval
- Performs BM25 lexical retrieval
- Combines both using Reciprocal Rank Fusion (RRF)
- Blends attack-specific retrieval with a general OT/ICS incident-response guidance query
- Returns the final retrieved chunks with metadata

---

## 3) `evaluator.py`
This file evaluates:
- Retrieval quality
- Report quality
- Section completeness
- OT/ICS terminology use
- Technical depth
- Actionability
- Severity justification
- Lexical grounding
- Source utilisation
- Environment specificity
- Uncertainty handling
- Benign alternative explanations
- Penalties for unsupported or hallucinated claims

---

# How to run

## 1) Open PowerShell in this deployment folder
```powershell
cd "path\to\stage3_deploy"
```
## 2) Create a new virtual environment
```powershell
python -m venv stage3_env
```

## 3) Activate the virtual environment
```powershell
stage3_env\Scripts\activate
```

## 4) Upgrade pip
```powershell
python -m pip install --upgrade pip
```

## 5) Install requirements
```powershell
pip install -r requirements.txt
```

## 6) Set the Groq API key
```powershell
set GROQ_API_KEY=your_own_key
```

---

# Extra:

## 7) Run the deployment with the default alerts file
```powershell
python run_deployment.py
```

## 8) Run the deployment with a specific alerts file
```powershell
python run_deployment.py --alerts_path outputs/stage2/alerts.json
```

---

## 10) Deactivate the virtual environment after finishing
```powershell
deactivate
```

---
