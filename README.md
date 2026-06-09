# AegisOps 

**Google Cloud Agent Hackathon 2026 Submission**

Monitoring is passive. Engineers still investigate and fix drift manually. 
**AegisOps** is the autonomous MLOps engineer — it detects, diagnoses, and acts.

Built with **Google ADK v2.2.0** and **Gemini 2.5 Flash**, AegisOps intercepts live telemetry from Arize Phoenix (via MCP) and autonomously triggers GCP remediation workflows.

---

##  Architecture

AegisOps operates on a strict *Observe → Reason → Act* loop.

```mermaid
graph TD
    A[Arize Phoenix] -->|Drift Event via MCP| B(Google ADK Runner)
    B --> C{Gemini 2.5 Flash Brain}
    
    C -->|Moderate Severity| D[Tool: Isolate Data Batch]
    D -->|GCS API| E[(Cloud Storage Quarantine)]
    
    C -->|Moderate Severity| F[Tool: Trigger Retraining]
    F -->|Vertex API| G[Vertex AI PipelineJob]
    
    C -->|Critical Severity| H[Tool: Rollback Deployment]
    H -->|Cloud Run Admin API| I[Cloud Run Stable Revision]
    
    C -->|Low Severity / Final Step| J[Tool: Generate Incident Report]
    J --> K[JSON + Text Report in /incidents]
```

##  Key Features

- **Zero Manual Intervention**: Replaces the PagerDuty → Investigation → Remediation cycle entirely.
- **Strict JSON Contracts**: Telemetry is parsed through a strict `DriftEvent` schema to prevent hallucinations.
- **Dual-Mode Tools**: Tools execute real GCP API calls when `GOOGLE_APPLICATION_CREDENTIALS` is present, but seamlessly fall back to mock mode for easy local demoing.
- **Exponential Backoff**: Built-in `@with_retry` decorator handles transient GCP API limits or networking blips.
- **Audit Trails**: Every action produces a timestamped, structured incident report.

---

##  Tech Stack

- **Agent Orchestration**: Google ADK (Agent Development Kit) v2.2.0
- **LLM Engine**: Gemini 2.5 Flash (fast reasoning)
- **Observability / Input**: Arize Phoenix (via MCP `StdioConnectionParams`)
- **Remediation Actions**: 
  - Google Cloud Storage (Batch isolation)
  - Vertex AI (Pipeline retraining)
  - Cloud Run (Traffic rollback)

---

##  Quickstart (Demo Mode)

You can run the agent locally without any GCP configuration. The tools will auto-detect the lack of credentials and run in **Mock Mode**, simulating the remediation actions.

### 1. Install Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment
Create a `.env` file in the root:
```env
GOOGLE_GENAI_API_KEY=your_gemini_api_key
GOOGLE_API_KEY=your_gemini_api_key
```

### 3. Run the Interactive CLI Demo
```bash
python -m src.main
```
This boots the agent and presents 3 telemetry scenarios (Moderate Drift, Critical Degradation, Stable Operations). Choose one to watch Gemini reason and call the appropriate mock tools.

### 4. Run the ADK Web UI
Google ADK provides a beautiful chat interface out of the box:
```bash
adk web .
```

---

##  Live GCP Mode (Optional)

To execute real remediation actions:
1. Authenticate with Google Cloud:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
   ```
2. Set your environment variables in `.env`:
   ```env
   GOOGLE_CLOUD_PROJECT=your-project-id
   GOOGLE_CLOUD_LOCATION=us-central1
   GCS_DATA_BUCKET=your-data-bucket
   VERTEX_PIPELINE_TEMPLATE=gs://your-bucket/template.json
   ```
3. Run the agent. The dual-mode tools will automatically detect the credentials and use the real APIs.
