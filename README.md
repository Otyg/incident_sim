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

## Så är applikationen tänkt att användas

Applikationen är byggd som ett enkelt övningsstöd för en incidentövning där en deltagare eller facilitator kan gå igenom ett scenario steg för steg i webbläsaren.

Ett typiskt användarflöde ser ut så här:

1. Starta applikationen lokalt med `uvicorn src.main:app --reload`.
2. Öppna startsidan i webbläsaren.
3. Välj ett sparat scenario från databasen, klicka på `Ladda scenario` för exempelscenariot eller ladda upp ett eget scenario i JSON-format.
4. Läs scenarioöversikten för att förstå kontext, mål och svårighetsgrad.
5. Klicka på `Starta session` för att skapa en ny övningssession från scenariot.
6. Följ panelen `Aktuell session` för att se nuvarande fas, tid, turn-nummer och centrala metrics.
7. Skriv in en deltagaråtgärd i formuläret `Deltagaråtgärd`.
8. Skicka åtgärden för att spela en turn.
9. Läs `Senaste lägesbild` för att se systemets återkoppling på den senaste turnen.
10. Följ `Tidslinje` för att se alla tidigare turns i ordning.

## Vad användaren ser i gränssnittet

Gränssnittet består av fem huvuddelar:

- `Scenarioöversikt`: visar vilket scenario som är inläst, dess beskrivning, mål och tidsram.
- `Scenariokontroller`: visar sparade scenarion i databasen och låter användaren ladda upp nya scenarion i JSON-format.
- `Aktuell session`: visar det senaste session-state som backend har sparat.
- `Deltagaråtgärd`: ett fritextfält där användaren beskriver nästa åtgärd i övningen.
- `Senaste lägesbild`: visar den senaste narrationen och de viktigaste punkterna efter en turn.
- `Tidslinje`: visar sparade turns i kronologisk ordning.

## Nuvarande beteende och begränsningar för en användare

Det är viktigt att känna till hur den nuvarande versionen fungerar:

- Applikationen använder ett inbyggt exempelscenario i frontend.
- Sessioner och tidslinje lagras bara i minnet så länge processen kör.
- Om servern startas om försvinner scenarier, sessioner och turns.
- Ollama kan användas som faktisk runtime-provider om `config.yaml` pekar på en fungerande lokal eller molnbaserad Ollama-instans.
- `openai` finns fortfarande bara som stub och kommer därför att ge ett kontrollerat fel om den väljs i konfigurationen.

Det innebär att applikationen redan nu kan köras med ett riktigt providerflöde via Ollama, men att alla alternativa providers ännu inte är fullt implementerade.

Observera att turn-endpointen använder det konfigurerade providerlagret från `config.yaml`. Projektet stöder nu Ollama som runtime-provider, både mot lokal Ollama och Ollama Cloud. `openai` finns fortfarande kvar som stub och returnerar ett kontrollerat fel (`503`) tills en riktig integration implementeras.

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

## Konfiguration via `config.yaml`

Applikationen läser nu både storage-backend och LLM-provider från `config.yaml` i projektroten.

Exempel:

```yaml
storage:
  backend: tinydb
  tinydb:
    path: data/incident_sim.json

llm_provider:
  provider: ollama
  ollama:
    host: http://localhost:11434
    model: llama3.2
    interpret_model: llama3.2
    narration_model: llama3.2
    api_key: null
  openai:
    api_key: null
    base_url: null
    model: null
```

För storage gäller just nu:
- `tinydb`: lagrar data i en JSON-fil via TinyDB
- `in_memory`: håller data i processen utan filpersistens

För TinyDB kan du konfigurera:
- `storage.tinydb.path`: sökväg till JSON-filen som ska användas för lagring

## Scenarioformat

Scenarioformatet är nu dokumenterat separat:

- JSON Schema: [data/scenarios/scenario.schema.json](/home/maves/projects/incident_sim/data/scenarios/scenario.schema.json)
- Scenarioguide: [data/scenarios/README.md](/home/maves/projects/incident_sim/data/scenarios/README.md)

Guiden beskriver vad fälten betyder, hur nivåer som `impact_level` och
`severity` bör tolkas, och hur du bör lägga till faser, triggers och regler.

## Loggning

Backenden loggar nu händelser i tre nivåer:
- `info`: generell information om vad backend gör
- `warning`: fel som hanteras och som inte stoppar processen helt
- `error`: blockerande fel

Standardbeteendet är:
- `info` skrivs till `stdout`
- `warning` och `error` skrivs till `stderr`

Om du vill logga till fil, lägg till detta i `config.yaml`:

```yaml
logging:
  file: logs/backend.log
```

Relativa sökvägar tolkas relativt till katalogen där `config.yaml` ligger.
När fil-loggning är aktiv skrivs alla nivåer till filen, medan `warning` och
`error` fortfarande också skrivs till `stderr`.

## För administratör: så konfigureras LLM-åtkomsten

En administrativ användare behöver i praktiken bara arbeta i `config.yaml`.

Välj provider här:

```yaml
llm_provider:
  provider: ollama
```

Konfigurera sedan motsvarande block för den providern.

Exempel för lokal Ollama:

```yaml
llm_provider:
  provider: ollama
  ollama:
    host: http://localhost:11434
    model: llama3.2
    interpret_model: llama3.2
    narration_model: llama3.2
    api_key: null
```

Exempel för Ollama Cloud:

```yaml
llm_provider:
  provider: ollama
  ollama:
    host: https://ollama.com
    model: qwen3-coder:480b-cloud
    interpret_model: qwen3-coder:480b-cloud
    narration_model: qwen3-coder:480b-cloud
    api_key: DIN_OLLAMA_API_NYCKEL
```

Det viktigaste för en administratör är:
- `provider` styr vilken runtime-provider appen använder
- `host` styr vart anropen skickas
- `api_key` används när providern kräver autentisering
- `model` är standardmodell
- `interpret_model` och `narration_model` kan användas om olika steg ska ha olika modeller

Efter ändring i `config.yaml` startas appen om för att läsa in ny konfiguration.

Stödda provider-värden just nu:
- `ollama`: väljer `OllamaProvider`
- `openai`: väljer `OpenAIProvider`, som fortfarande är en stub

För Ollama kan du konfigurera:
- `host`: URL till lokal Ollama eller Ollama Cloud
- `api_key`: API-nyckel för cloud-anrop
- `model`: standardmodell
- `interpret_model`: valfri separat modell för action-interpretation
- `narration_model`: valfri separat modell för narration

Användning lokalt:
- sätt `llm_provider.provider: ollama`
- sätt `llm_provider.ollama.host: http://localhost:11434`
- välj modell i `llm_provider.ollama.model`

Användning mot Ollama Cloud:
- sätt `llm_provider.provider: ollama`
- sätt `llm_provider.ollama.host: https://ollama.com`
- sätt `llm_provider.ollama.api_key`
- välj en cloud-kompatibel modell

## För utvecklare: så lägger du till en ny LLM-provider

Providerlagret är byggt för att kunna utökas utan att API-lagret behöver göras om.

En utvecklare som vill lägga till en ny provider gör normalt följande:

1. Skapa en ny klass i [src/services/llm_provider.py](/home/maves/projects/incident_sim/src/services/llm_provider.py) eller bryt ut den till en närliggande modul om filen blir för stor.
2. Låt klassen implementera `LLMProvider`.
3. Säkerställ att `interpret_action()` returnerar en `dict` som matchar `InterpretedAction`.
4. Säkerställ att `generate_narration()` returnerar en `dict` som matchar `NarratorResponse`.
5. Lägg till ett nytt konfigurationsblock i `config.yaml` under `llm_provider`.
6. Uppdatera `get_llm_provider()` så att den kan välja den nya providern.
7. Lägg till tester för konfiguration, felhantering och payload-format.

Designregler som bör följas:
- låt providern returnera råa dictionaries och låt den centrala schema-valideringen ligga kvar
- låt autentisering, host och modellval komma från `config.yaml`
- håll affärslogik utanför providern
- återanvänd promptfilerna eller lägg till nya promptfiler om formatet kräver det

## Mock-provider, Ollama och andra providers

Projektet har två olika användningssätt för providerlagret just nu:

- Mock-provider: används bara i testsviten via `tests/mock_llm_provider.py` för att göra API- och providerscenarier deterministiska
- Ollama-provider: runtime-koden kan prata med både lokal Ollama och Ollama Cloud via den officiella Python-klienten `ollama`, styrd via `config.yaml`
- OpenAI-provider: finns kvar som stub för framtida integration

Det betyder att testerna kan köra ett komplett turn-flöde med mock, medan lokal körning nu kan använda Ollama som faktisk runtime-provider om rätt miljövariabler och modell finns tillgängliga.
