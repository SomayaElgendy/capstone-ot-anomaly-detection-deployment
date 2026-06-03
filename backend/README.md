# capstone-ot-anomaly-detection
# Capstone: OT Anomaly Detection & Incident Response
AI-powered system for detecting APT attacks in Operational Technology environments and generating automated incident responses.

## 🏗️ Architecture
```
OT Simulator → Redis Streams → AI Models → Redis Streams → Django Backend → Dashboard
```

## 📁 Project Structure

- **`backend/`** - Django REST API (Authentication, Database, APIs)
- **`ai-models/`** - ML models for anomaly detection and clustering
- **`ot-simulator/`** - ICS simulation tool + attack scenarios
- **`shared/`** - Common schemas and configurations

### Quick Start
```bash
# Clone the repository
git clone https://github.com/YOUR-USERNAME/capstone-ot-anomaly-detection.git
cd capstone-ot-anomaly-detection


## 📋 Development Workflow

1. **Create a feature branch**:
```bash
   git checkout -b feature/your-feature-name
```

2. **Work in your directory** (backend/, ai-models/, or ot-simulator/)

3. **Commit and push**:
```bash
   git add .
   git commit -m "feat: description of changes"
   git push origin feature/your-feature-name
```

4. **Create Pull Request** on GitHub

## 🔗 Integration Points

All services communicate via **Redis Streams**. See `shared/redis_schemas/` for message formats.
