# Scenarioguide

Den här guiden beskriver hur ett scenario i `incident_sim` är uppbyggt, hur fälten ska tolkas och vilka skrivkonventioner som rekommenderas.

Tillhörande JSON Schema finns i [scenario.schema.json](scenario.schema.json).

## Översikt

Ett scenario består av:

- metadata om scenario och målgrupp
- bakgrund och initialt läge
- aktörer
- inject-katalog
- dokumenterade regler
- exekverbara regler
- presentationsriktlinjer per målgrupp

Det är viktigt att skilja på:

- validering: vad som faktiskt kontrolleras av Pydantic och JSON Schema
- författningskonvention: hur fälten bör användas för att bli begripliga och konsekventa
- exekvering: vad backend faktiskt använder dynamiskt under körning

## Viktigt om nuvarande implementation

Alla scenariofält valideras och lagras, men backend exekverar inte alla delar dynamiskt.

Nuvarande läge:

- `initial_state.phase` lagras och visas, men styr inte någon automatisk fasmaskin i backend.
- `initial_state.initial_narration` används dynamiskt vid sessionsstart och ersätter tidigare LLM-genererad initial lägesbild.
- `inject_catalog[].trigger_conditions` är dokumentation för när injectet är tänkt att användas. De utvärderas inte generiskt av backend.
- `rules[]` beskriver scenariots tänkta orsak-verkan-samband, men backend läser idag inte in och kör dessa regler generiskt från scenariot.
- Den faktiska deterministiska regelmotorn finns i [rules_engine.py](../../src/services/rules_engine.py).

Det betyder att scenarioförfattaren nu kan styra faser, inject-aktivering och vissa stateförändringar direkt i JSON, medan mer avancerad logik fortfarande kan kräva backendkod.

## Rotnivå

### `id`

Unikt scenario-id. Använd ett stabilt, maskinläsbart format.

Rekommendation:

- använd små bokstäver
- använd bindestreck
- inkludera gärna domän och löpnummer

Exempel:

```json
"id": "scenario-municipality-ransomware-001"
```

### `title`

Det namn som visas för användaren.

### `version`

Fri versionsbeteckning, till exempel `1.0` eller `2026-03`.

### `description`

Kort sammanfattning av scenariot. Ska ge tillräcklig kontext för att förstå upplägget utan att läsa hela bakgrunden.

### `audiences`

Vilka målgrupper scenariot är avsett för.

Tillåtna värden:

- `krisledning`
- `it-ledning`
- `kommunikation`

### `training_goals`

Lista över vad scenariot ska öva. Varje mål bör beskriva en konkret förmåga.

Bra exempel:

- `Öva initial lägesuppfattning under osäkerhet`
- `Öva extern kommunikation under högt medietryck`

### `difficulty`

Övergripande svårighetsgrad för scenariot.

Tillåtna värden:

- `low`
- `medium`
- `high`

Rekommenderad tolkning:

- `low`: begränsat antal samtidiga problem, tydligt beslutsläge
- `medium`: flera samtidiga avvägningar men hanterbart tempo
- `high`: hög osäkerhet, flera beroenden, stark tidspress och tydlig verksamhetspåverkan

### `timebox_minutes`

Planerad maximal övningstid i minuter. Tillåtna värden är `1-480`.

## `background`

Bakgrunden beskriver förutsättningarna innan övningen börjar.

### `organization_type`

Kort typ av organisation, till exempel `kommun`, `myndighet` eller `region`.

### `context`

Bakgrundstext som placerar scenariot i tid, verksamhet och organisatorisk kontext.

### `threat_actor`

Kort beskrivning av den som orsakar incidenten eller hotet.

### `assumptions`

Lista över antaganden som gäller i scenariot. Dessa hjälper deltagarna att förstå vad de får utgå ifrån utan att behöva fråga om allt.

## `initial_state`

Detta beskriver läget när övningen startar.

### `time`

Starttid. Rekommenderat format är `HH:MM`.

### `phase`

Namn på startfasen. Det här är i dag ett scenariobegrepp, inte en dynamisk motorstyrd fasväxel i backend.

Rekommenderad skrivregel:

- använd ett kort, stabilt, maskinläsbart fas-id
- använd små bokstäver och bindestreck

Bra exempel:

- `initial-detection`
- `triage`
- `containment`
- `service-disruption`
- `recovery`
- `post-incident`

Praktiskt råd:

- om ni inför egna faser, håll er till samma namn genom hela scenariot, dokumentationen och eventuell framtida kod

### `known_facts`

Det deltagarna vet när övningen startar.

Bra innehåll:

- observerade symptom
- inkomna rapporter
- verifierade fakta

### `unknowns`

Det deltagarna ännu inte vet men behöver utreda.

Bra innehåll:

- omfattning
- angriparens närvaro
- dataförlust eller exfiltration
- tid till återställning

### `affected_systems`

System eller tjänster som redan bedöms påverkade i startläget.

### `business_impact`

Hur verksamheten påverkas när scenariot startar.

### `impact_level`

Övergripande påverkan i startläget på en femgradig skala.

Rekommenderad tolkning:

- `1`: mycket begränsad påverkan, mest lokal störning
- `2`: märkbar påverkan men inom ett begränsat område
- `3`: tydlig påverkan på flera funktioner eller verksamhetsdelar
- `4`: allvarlig påverkan på kritiska verksamheter, hög tidspress
- `5`: extrem påverkan, långvarig eller samhällskritisk störning

Exempel:

- `impact_level: 3` betyder ungefär att läget redan är tydligt allvarligt, påverkar flera delar av verksamheten och kräver samordning, men att hela organisationen ännu inte nödvändigtvis står stilla.

### `initial_narration`

Fördefinierat startnarrativ som skickas tillbaka från backend när en session startas.

Detta fält används nu i stället för att generera initial lägesbild via LLM.

Struktur:

- `default`: gemensamt startnarrativ för alla målgrupper
- `by_audience`: valfria målgruppsspecifika narrativ

Prioritetsregel vid sessionsstart:

- backend använder först `by_audience` för vald målgrupp om den finns
- annars används `default`

Varje narrativ följer samma struktur som en vanlig narration i API:t:

- `situation_update`
- `key_points`
- `new_consequences`
- `injects`
- `decisions_to_consider`
- `facilitator_notes`

Praktiskt råd:

- lägg alltid in ett `default`-narrativ även om ni också använder `by_audience`
- använd `by_audience` när olika målgrupper ska få olika fokus redan i startläget

## `actors`

Aktörer beskriver viktiga roller i scenariot.

### `id`

Stabilt maskinläsbart id, till exempel `actor-ciso`.

### `name`

Visningsnamn.

### `role`

Kort beskrivning av vad aktören gör eller ansvarar för.

## `inject_catalog`

Inject-katalogen beskriver möjliga inspel som facilitatorn kan använda för att öka tryck, bredda perspektiv eller driva fram beslut.

### `type`

Tillåtna värden:

- `media`
- `executive`
- `operations`
- `technical`
- `stakeholder`

Använd dem så här:

- `media`: frågor från media eller offentlighet
- `executive`: frågor från ledning, politisk nivå eller styrning
- `operations`: påverkan på verksamheten
- `technical`: tekniska fynd, driftproblem eller systemsignal
- `stakeholder`: externa intressenter, partner, leverantörer eller andra berörda

### `title`

Kort rubrik som snabbt signalerar injectets innehåll.

### `description`

Själva injectet i textform.

### `trigger_conditions`

Det här fältet är i dag dokumentation, inte en exekverad regel.

Skriv trigger-villkor som:

- konkreta
- observerbara
- korta

Bra exempel:

- `Ingen extern kommunikation efter två turns`
- `Service_disruption når nivå 2 eller högre`
- `Krisledning aktiverad men ingen teknisk isolering beslutad`

Sämre exempel:

- `När det känns rimligt`
- `Om läget blir värre`

Rekommendation:

- skriv triggers som om de senare skulle kunna översättas till riktig maskinlogik
- använd samma begrepp som i regler, metrics och faser

### `audience_relevance`

Vilka målgrupper injectet primärt angår.

### `severity`

Hur skarpt injectet är på en femgradig skala.

Rekommenderad tolkning:

- `1`: låg intensitet, mest informationsgivande
- `2`: lätt tryckökning, kräver uppmärksamhet
- `3`: tydligt handlingsdrivande, skapar ett aktivt beslutsläge
- `4`: allvarligt inject som kraftigt ökar tidspress eller verksamhetspåverkan
- `5`: mycket skarpt inject som omedelbart bör påverka prioriteringar och ledningsnivå

Exempel:

- `severity: 4` i ett operations-inject betyder att injectet bör uppfattas som tydligt allvarligt och kräva snabb prioritering, inte bara fungera som bakgrundsbrus.

## `rules`

Regler beskriver scenariots tänkta logik, men körs inte från JSON.

Använd dem därför som:

- dokumentation för scenarioförfattare
- underlag för framtida automation
- stöd för facilitatorn

## `executable_rules`

Det här är den körbara delen av scenariot i v1.

Varje regel innehåller:

- `trigger`: när regeln ska utvärderas
- `conditions`: alla villkor som måste vara uppfyllda
- `effects`: vad som ska hända om regeln träffar
- `priority`: `high`, `medium` eller `low`
- `once`: om regeln bara får slå till en gång per session

### `trigger`

Tillåtna värden i v1:

- `session_started`
- `turn_processed`

### `conditions`

Varje villkor består av:

- `fact`
- `operator`
- `value`

Tillåtna `fact` i v1:

- `state.phase`
- `state.metrics.*`
- `state.flags.*`
- `session.turn_number`
- `action.action_types`
- `action.targets`

Tillåtna operatorer i v1:

- `equals`
- `not_equals`
- `gte`
- `lte`
- `contains`
- `not_contains`

### `effects`

Tillåtna effekter i v1:

- `set_phase`
- `add_active_inject`
- `resolve_inject`
- `append_focus_item`
- `append_consequence`
- `increment_metric`
- `set_flag`
- `append_exercise_log`

Praktiskt råd:

- använd `append_exercise_log` när du vill att övningsledaren tydligt ska se varför något ändrades i UI:t
- använd `once: true` för fasbyten och inject-aktiveringar som bara ska ske en gång
- använd `priority: high` för regler som bör slå till före mer allmänna uppdateringar

### `conditions`

Villkor som borde leda till en effekt.

Rekommenderad skrivregel:

- skriv varje villkor som ett kort påstående
- använd etablerade begrepp som action-types, mål, metrics, flags eller fas

Bra exempel:

- `containment riktad mot vpn eller external_access`
- `ingen communication under två turns`
- `impact_level minst 4`

### `effects`

Den tänkta följden om villkoren uppfylls.

Bra exempel:

- `öka media_pressure`
- `lägg till inject-media-001`
- `sätt executive_escalation`
- `lägg till fokus på extern kommunikation`

## `presentation_guidelines`

Riktlinjer för hur scenariot bör spelas för respektive målgrupp.

### `focus`

Vilka aspekter som ska framhävas för målgruppen.

### `tone`

Vilken tonalitet presentationen ska ha, till exempel `strategisk`, `operativ` eller `samordnande`.

## Hur du lägger till faser

Faser är fria strängar, men används nu också av den datadrivna scenariomotorn.

För att lägga till en ny fas:

1. välj ett kort fas-id i kebab-case
2. sätt det som `initial_state.phase` om det är startläget
3. använd samma fasnamn konsekvent i scenario, dokumentation och regler
4. lägg till en `set_phase`-effekt i `executable_rules` när en senare fas ska aktiveras

Bra uppsättning:

- `initial-detection`
- `triage`
- `containment`
- `stabilization`
- `recovery`

Undvik:

- flera nästan likadana namn för samma sak
- naturligt språk med varierande stavning
- interna förkortningar som bara en person förstår

## Hur du lägger till triggers

För dokumentation kan du fortfarande använda `inject_catalog[].trigger_conditions`.

För faktisk exekvering i v1 används:

- `trigger` på regeln
- ett eller flera strukturerade `conditions`

Bra arbetsmodell:

1. välj först om regeln ska köras vid `session_started` eller `turn_processed`
2. skriv sedan villkor utifrån observerbara facts som metrics, flags, phase eller action-types
3. håll varje villkor kort och maskinläsbart

Bra exempel:

- `media_pressure når 2`
- `ingen extern kommunikation efter två turns`
- `service_disruption ökar efter containment-beslut`

## Hur du lägger till regler

Om regeln bara ska dokumentera scenariots idé använder du `rules[]`.

Om regeln ska påverka körningen automatiskt använder du `executable_rules[]`.

Bra arbetsmodell:

1. bestäm när regeln ska utvärderas med `trigger`
2. välj bara de `conditions` som verkligen behövs
3. lägg till en eller flera `effects`
4. markera `once: true` om regeln inte ska kunna upprepas
5. lägg gärna till en `append_exercise_log`-effekt så att utfallet syns tydligt i UI:t

Exempel på vanlig regel:

```json
{
  "id": "rule-phase-containment",
  "name": "Byt till containment",
  "trigger": "turn_processed",
  "conditions": [
    {
      "fact": "state.flags.external_access_restricted",
      "operator": "equals",
      "value": true
    }
  ],
  "effects": [
    {
      "type": "set_phase",
      "phase": "containment"
    },
    {
      "type": "append_exercise_log",
      "log_type": "scenario_event",
      "message": "Scenariot går in i containment."
    }
  ],
  "priority": "high",
  "once": true
}
```

## Validering

Scenarion valideras i applikationen av Pydantic-modellen `Scenario`, men den
modellen använder nu den incheckade JSON Schema-filen som källa för själva
scenariovalideringen.

Det innebär att:

- `scenario.schema.json` är source of truth för scenariots regler
- uppladdning och backendvalidering följer schemafilen
- `Scenario.model_json_schema()` returnerar den incheckade schemafilen i stället
  för en separat genererad variant

För extern validering kan du använda:

- JSON Schema-filen [scenario.schema.json](scenario.schema.json)
- uppladdning via UI eller POST till `/scenarios`

## Exempel

Se exempelscenariot i [municipality_ransomware.json](municipality_ransomware.json).
