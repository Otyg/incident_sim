# Incident Exercise Prototype

En liten FastAPI-prototyp för scenario- och incidentövning med:
- scenario- och sessionmodeller
- enkel regelmotor
- prototypisk interpreter/narrator
- validering med Pydantic
- unit-tester med pytest

## Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Tester

```bash
PYTHONPATH=. pytest
```
