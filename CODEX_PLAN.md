# CODEX_PLAN.md

## Syfte

Bygg en första fungerande version av en applikation för incidentövning där:

- ett scenario kan läsas in
- en målgrupp kan väljas
- deltagarnas åtgärder kan matas in i fritext
- systemet håller ett uppdaterat scenario-state
- en regelmotor uppdaterar läget deterministiskt
- en LLM-adapter tolkar åtgärder och genererar nästa lägesbild
- hela övningen sparas för återspelning och utvärdering

Projektet ska byggas inkrementellt i små, verifierbara steg.

---

## Övergripande arkitektur

### Backend
- Python
- FastAPI
- Pydantic för validering
- pytest för tester

### Domän
- Scenario
- SessionState
- Turn
- InterpretedAction
- NarratorResponse

### Services
- RulesEngine
- LLMProvider interface
- MockLLMProvider
- senare: riktig provider

### Storage
- börja med in-memory repository
- senare: SQLite/PostgreSQL

### Frontend
- enkel React/Next.js-klient i senare steg

---

## Arbetsprinciper för Codex

För varje steg gäller:

- Gör minsta nödvändiga ändring för att lösa uppgiften.
- Ändra inte orelaterade filer.
- Lägg alltid till eller uppdatera tester.
- Behåll tydlig separering mellan API, modeller, services och storage.
- Lägg inte affärslogik i routes.
- Validera all strukturerad LLM-output med schema innan den används.
- Om något är oklart: välj det enklaste rimliga alternativet.
- Sammanfatta alltid:
  - vilka filer som ändrades
  - vad som implementerades
  - vilka tester som kördes

---

## Definition of Done för MVP

MVP:n är klar när följande fungerar:

- scenario kan skapas och hämtas
- session kan startas från scenario
- deltagaråtgärd kan skickas in
- action interpreter returnerar validerbar struktur
- regelmotorn uppdaterar state
- narrator returnerar nästa lägesbild
- turn och tidslinje sparas
- testsvit täcker validering, regelmotor och centrala API-flöden
- appen går att köra lokalt via dokumenterade kommandon

---

## Rekommenderad projektstruktur

```text
app/
  api/
  models/
  schemas/
  services/
  storage/
  prompts/
  main.py
tests/
frontend/
Dockerfile
docker-compose.yml
README.md
```

---

# IMPLEMENTATIONSSTEG

## Steg 1 — Stabil backend och health endpoint

### Mål
Gör projektet körbart lokalt med FastAPI och grundläggande teststöd.

### Uppgift till Codex
1. Säkerställ att `app/main.py` exponerar en FastAPI-app.
2. Lägg till `GET /health` som returnerar:
   ```json
   {"status": "ok"}
   ```
3. Säkerställ att projektet går att starta med:
   ```bash
   uvicorn app.main:app --reload
   ```
4. Lägg till pytest-konfiguration om den saknas.
5. Lägg till ett test för `/health`.

### Definition av klart
- Appen startar utan importfel.
- `/health` returnerar 200.
- Testet för `/health` passerar.

### Validering
- Kör relevanta tester.
- Lista ändrade filer.
- Sammanfatta resultat.

### Prompt till Codex
```text
Du arbetar i ett Python/FastAPI-projekt för en incidentövningsapp.

Uppgift:
Stabilisera backend-skelettet och gör projektet körbart lokalt.

Gör följande:
1. Säkerställ att app/main.py exponerar en FastAPI-app.
2. Lägg till GET /health som returnerar {"status":"ok"}.
3. Säkerställ att projektet går att starta med uvicorn app.main:app.
4. Lägg till pytest-konfiguration om den saknas.
5. Skriv ett test som verifierar att /health returnerar 200 och status ok.

Begränsningar:
- Ändra inte affärslogik ännu.
- Behåll kodstrukturen enkel.
- Lägg inte till databas ännu.

Definition av klart:
- Appen startar lokalt utan importfel.
- /health fungerar.
- Testet passerar.

Validering:
- Kör relevanta tester.
- Sammanfatta ändrade filer och resultat.
```

---

## Steg 2 — Domänmodeller och validering

### Mål
Inför tydliga Pydantic-modeller och strikt validering.

### Uppgift till Codex
Implementera modeller för:

- `Scenario`
- `SessionState`
- `Turn`
- `InterpretedAction`
- `NarratorResponse`

Lägg till:
- literals/enums för action types
- literals/enums för inject types
- priority-fält
- validering för obligatoriska fält
- validering av rimliga värdeintervall

### Definition av klart
- Giltiga payloads parse:ar korrekt.
- Ogiltiga payloads ger valideringsfel.
- Testfall finns för både giltiga och ogiltiga exempel.

### Validering
- kör valideringstester
- redovisa ändrade filer

### Prompt till Codex
```text
Du arbetar i ett Python/FastAPI-projekt för en incidentövningsapp.

Uppgift:
Implementera domänmodeller och validering med Pydantic.

Gör följande:
1. Definiera modeller för Scenario, SessionState, Turn, InterpretedAction och NarratorResponse.
2. Lägg till relevanta Literal/Enum-värden för action types, inject types och priority.
3. Säkerställ att ogiltiga payloads ger tydliga valideringsfel.
4. Lägg till tester för giltiga och ogiltiga exempel.

Begränsningar:
- Implementera endast modeller och validering.
- Lägg inte till API-logik eller persistence i detta steg.

Definition av klart:
- Modellerna kan importeras utan fel.
- Giltiga objekt valideras korrekt.
- Ogiltiga objekt ger valideringsfel.
- Tester passerar.

Validering:
- Kör relevanta tester.
- Sammanfatta ändrade filer och resultat.
```

---

## Steg 3 — In-memory repository och API-endpoints

### Mål
Gör det möjligt att skapa scenario, starta session och spela en tur.

### Uppgift till Codex
Skapa ett enkelt repository-lager och implementera endpoints:

- `POST /scenarios`
- `GET /scenarios/{id}`
- `POST /sessions`
- `GET /sessions/{id}`
- `POST /sessions/{id}/turns`

Använd in-memory storage i detta steg.

### Definition av klart
- Scenario kan skapas och hämtas.
- Session kan startas från scenario.
- En turn kan skickas in och ge ett grundläggande svar.
- API-tester finns.

### Validering
- kör API-integrationstester
- sammanfatta flödet

### Prompt till Codex
```text
Du arbetar i ett Python/FastAPI-projekt för en incidentövningsapp.

Uppgift:
Implementera in-memory repository och grundläggande API-endpoints.

Gör följande:
1. Lägg till ett enkelt repository-lager i minnet.
2. Implementera endpoints:
   - POST /scenarios
   - GET /scenarios/{id}
   - POST /sessions
   - GET /sessions/{id}
   - POST /sessions/{id}/turns
3. Se till att session kan startas från ett befintligt scenario.
4. Lägg till API-tester för dessa endpoints.

Begränsningar:
- Använd endast in-memory persistence.
- Lägg inte till databas ännu.
- Håll affärslogik utanför routes så långt det går.

Definition av klart:
- Scenario kan skapas och hämtas.
- Session kan startas.
- Turn-endpointen fungerar på grundnivå.
- Tester passerar.

Validering:
- Kör relevanta tester.
- Sammanfatta ändrade filer och resultat.
```

---

## Steg 4 — Regelmotor MVP

### Mål
Inför deterministiska state-ändringar baserat på deltagarnas åtgärder.

### Uppgift till Codex
Implementera en enkel regelmotor med stöd för:

- containment + external access
- communication / ingen communication
- escalation
- metrics-uppdatering
- consequences
- flags
- focus items

Separera tydligt mellan:

- interpretation
- rules/state update
- narration

### Definition av klart
- State uppdateras deterministiskt.
- Relevanta metrics, flags och consequences ändras korrekt.
- Testfall täcker centrala regler.

### Validering
- kör parametriserade tester för regelmotor
- dokumentera vilka regler som införts

### Prompt till Codex
```text
Du arbetar i ett Python/FastAPI-projekt för en incidentövningsapp.

Uppgift:
Implementera en enkel regelmotor för state transitions.

Gör följande:
1. Lägg till en RulesEngine-service.
2. Stöd minst följande fall:
   - containment mot external_access
   - communication respektive utebliven communication
   - escalation
3. Uppdatera state genom metrics, flags, consequences och fokuspunkter.
4. Lägg till parametriserade tester för regelmotorn.

Begränsningar:
- Håll logiken enkel och deterministisk.
- Lägg inte in LLM-anrop i regelmotorn.
- Affärslogik ska ligga i services, inte i routes.

Definition av klart:
- Regelmotorn uppdaterar state korrekt.
- Reglerna är testade.
- Tester passerar.

Validering:
- Kör relevanta tester.
- Sammanfatta ändrade filer, regler och resultat.
```

---

## Steg 5 — LLM-adapter med mock-provider

### Mål
Gör LLM-lagret utbytbart.

### Uppgift till Codex
Skapa ett provider-interface med två operationer:

- `interpret_action(...)`
- `generate_narration(...)`

Implementera:

- `MockLLMProvider`
- `OpenAIProvider` som stub eller feature-flagged implementation
- promptfiler under `app/prompts/`

Säkerställ att structured output valideras innan den används.

### Definition av klart
- Appen kan köras helt med mock-provider.
- Provider kan bytas via miljövariabel.
- Felaktig provider-output hanteras kontrollerat.

### Validering
- kör tester för mock-provider
- verifiera schemafelshantering

### Prompt till Codex
```text
Du arbetar i ett Python/FastAPI-projekt för en incidentövningsapp.

Uppgift:
Inför ett LLM-provider-interface med mock-provider.

Gör följande:
1. Skapa ett provider-interface med metoderna interpret_action och generate_narration.
2. Implementera en MockLLMProvider som returnerar validerbara strukturer.
3. Lägg till en OpenAIProvider som stub eller feature-flagged implementation.
4. Lägg prompts i separata filer under app/prompts.
5. Validera all provider-output innan den används i applikationen.

Begränsningar:
- Mock-provider ska vara standard.
- OpenAIProvider behöver inte vara fullständigt integrerad mot extern tjänst ännu.
- Ändra inte orelaterad logik.

Definition av klart:
- Mock-provider fungerar.
- Provider kan väljas via konfiguration.
- Output valideras och fel hanteras kontrollerat.
- Tester passerar.

Validering:
- Kör relevanta tester.
- Sammanfatta ändrade filer och resultat.
```

---

## Steg 6 — Audit log och tidslinje

### Mål
Spara hela övningsförloppet för återspelning och analys.

### Uppgift till Codex
Spara varje turn med:

- participant input
- interpreted action
- state diff eller state snapshot
- narrator response

Lägg till endpoint:

- `GET /sessions/{id}/timeline`

### Definition av klart
- Flera turns lagras i korrekt ordning.
- Tidslinjen kan läsas tillbaka.
- Test finns för historik och ordning.

### Validering
- kör tester för timeline
- verifiera att data sparas komplett

### Prompt till Codex
```text
Du arbetar i ett Python/FastAPI-projekt för en incidentövningsapp.

Uppgift:
Lägg till audit log och tidslinje för varje session.

Gör följande:
1. Spara varje turn med participant input, interpreted action, state-resultat och narrator response.
2. Lägg till endpointen GET /sessions/{id}/timeline.
3. Säkerställ att turns returneras i korrekt ordning.
4. Lägg till tester för tidslinjen.

Begränsningar:
- Behåll befintlig storage-struktur enkel.
- Fokusera på korrekthet och spårbarhet.

Definition av klart:
- Tidslinjen går att läsa ut.
- Flera turns sparas korrekt.
- Tester passerar.

Validering:
- Kör relevanta tester.
- Sammanfatta ändrade filer och resultat.
```

---

## Steg 7 — Enkel frontend

### Mål
Gör systemet användbart utan API-klient.

### Uppgift till Codex
Bygg en enkel frontend med:

- scenarioöversikt
- session state
- formulär för deltagaråtgärd
- tidslinje
- senaste lägesbild

### Definition av klart
- En användare kan starta en session och spela flera turns från browsern.
- Fel och loading states hanteras på grundnivå.

### Validering
- kör frontend lokalt
- verifiera att backend-anrop fungerar

### Prompt till Codex
```text
Du arbetar i ett projekt för en incidentövningsapp med FastAPI-backend.

Uppgift:
Bygg en enkel frontend för att köra en övningssession från webbläsaren.

Gör följande:
1. Skapa en enkel React- eller Next.js-klient.
2. Lägg till vyer för:
   - scenarioöversikt
   - aktuell session state
   - senaste lägesbild
   - formulär för deltagaråtgärd
   - tidslinje
3. Koppla klienten till backendens endpoints.
4. Lägg till enkel felhantering och loading states.

Begränsningar:
- Håll UI:t enkelt.
- Fokusera på funktion framför design.
- Bygg inte avancerad autentisering.

Definition av klart:
- En användare kan starta och spela en session i browsern.
- Grundläggande flöde fungerar.
```

---

## Steg 8 — Docker, config och utvecklarupplevelse

### Mål
Gör projektet enkelt att köra och förstå för andra utvecklare.

### Uppgift till Codex
Lägg till:

- `Dockerfile`
- `docker-compose.yml`
- `.env.example`
- förbättrad `README.md`

README ska beskriva:

- installation
- körning
- tester
- miljövariabler
- hur mock-provider respektive riktig provider används

### Definition av klart
- Projektet går att starta med ett fåtal kommandon.
- README räcker för att en ny utvecklare ska komma igång.

### Validering
- verifiera att dokumenterade kommandon är rimliga
- sammanfatta ändrade filer

### Prompt till Codex
```text
Du arbetar i ett projekt för en incidentövningsapp.

Uppgift:
Förbättra developer experience med Docker och dokumentation.

Gör följande:
1. Lägg till Dockerfile.
2. Lägg till docker-compose.yml.
3. Lägg till .env.example.
4. Uppdatera README med:
   - installation
   - lokal körning
   - tester
   - miljövariabler
   - byte mellan mock-provider och riktig provider

Begränsningar:
- Håll konfigurationen enkel.
- Dokumentera endast det som faktiskt stöds av projektet.

Definition av klart:
- Projektet går att starta med dokumenterade steg.
- README är tydlig och praktisk.
```

---

# Gemensamma kvalitetsgrindar för varje steg

Codex ska alltid kontrollera:

- inga brutna imports
- inga oanvända centrala beroenden
- all LLM-output valideras med schema
- ingen affärslogik läcker in i route-lagret
- stateförändringar är deterministiska där de ska vara det
- tester finns för ny funktionalitet

---

# Gemensam svarsmall för Codex efter varje steg

Be Codex avsluta varje steg med:

1. Kort sammanfattning av vad som implementerats
2. Lista över ändrade filer
3. Eventuella antaganden
4. Vilka tester som kördes
5. Resultat av testerna
6. Eventuella kvarstående begränsningar

---

# Rekommenderad körordning

Kör stegen i denna ordning:

1. Stabil backend och health endpoint
2. Domänmodeller och validering
3. In-memory repository och API-endpoints
4. Regelmotor MVP
5. LLM-adapter med mock-provider
6. Audit log och tidslinje
7. Enkel frontend
8. Docker, config och README

---

# Viktiga begränsningar

Undvik att ge Codex ett enda stort uppdrag som omfattar:

- backend
- frontend
- Docker
- LLM-integration
- tester

allt samtidigt.

Ge i stället ett steg i taget och verifiera resultatet mellan varje steg.

Undvik också vaga uppdrag som:
- "gör appen bättre"
- "bygg klart allt"
- "lägg till AI"

Var explicit med scope, definition av klart och validering.

---

# Slutmål

När alla steg är genomförda ska projektet ha:

- körbar FastAPI-backend
- validerade domänmodeller
- turbaserad incidentövning
- regelstyrd state-hantering
- utbytbart LLM-lager
- spårbar tidslinje
- enkel frontend
- dokumenterad lokal körning
- testbar struktur för vidareutveckling
