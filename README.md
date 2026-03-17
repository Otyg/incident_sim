# Incident Exercise Prototype

En liten FastAPI-prototyp för scenario- och incidentövning med:
- validerade scenario-, session- och turnmodeller
- deterministisk regelmotor
- utbytbart providerlager för tolkning och lägesbild
- audit log och tidslinje
- enkel browserklient serverad från backend
- tester med `pytest`

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Lokal körning

Starta backend och frontend tillsammans via FastAPI:

```bash
uvicorn src.main:app --reload
```

Öppna sedan `http://127.0.0.1:8000/` i webbläsaren.

Observera att turn-endpointen använder det konfigurerade providerlagret. Med nuvarande kod kommer runtime-provider `openai` att svara med ett kontrollerat fel (`503`) tills en riktig integration implementeras. Browserklienten och testsviten använder därför olika vägar:
- browserklienten visar att frontend/backendyta är kopplad
- testsviten använder en testlokal mock-provider för att verifiera turn-flödet

## Tester

```bash
pytest
```

Du kan också köra de mest centrala delarna separat:

```bash
pytest -q tests/test_api.py
pytest -q tests/test_rules_engine.py
pytest -q tests/test_llm_provider.py
```

## Miljövariabler

Följande miljövariabel används av runtime-providerlagret:

```bash
export INCIDENT_SIM_LLM_PROVIDER=openai
```

Stödda värden just nu:
- `openai`: väljer `OpenAIProvider`, som i nuläget är en stub och returnerar ett kontrollerat fel när den används

## Mock-provider och riktig provider

Projektet har två olika användningssätt för providerlagret just nu:

- Mock-provider: används bara i testsviten via `tests/mock_llm_provider.py` för att göra API- och providerscenarier deterministiska
- Riktig provider: runtime-koden känner till `OpenAIProvider` via `INCIDENT_SIM_LLM_PROVIDER=openai`, men den är ännu inte integrerad mot en extern tjänst

Det betyder att testerna kan köra ett komplett turn-flöde, medan lokal browserkörning redan nu visar frontend, scenario/sessionflöde och felhantering för en ännu oimplementerad riktig provider.
