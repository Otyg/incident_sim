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

- `states[0]` används dynamiskt som startläge när en session skapas.
- `states[0].narration` används dynamiskt vid sessionsstart och ersätter tidigare LLM-genererad initial lägesbild.
- `inject_catalog[].trigger_conditions` är dokumentation för när injectet är tänkt att användas. De utvärderas inte generiskt av backend.
- `text_matchers[]` används dynamiskt för enkel, scenariostyrd matchning mot rå deltagartext innan regelmotorn körs.
- `target_aliases[]` används dynamiskt för att normalisera fria provider-targets och textbaserade uttryck till kanoniska target-värden före hints och regler.
- `interpretation_hints[]` används dynamiskt för att additivt komplettera LLM-tolkningen före regelutvärdering.
- `rules[]` beskriver scenariots tänkta orsak-verkan-samband, men backend läser idag inte in och kör dessa regler generiskt från scenariot.
- `executable_rules[]` används dynamiskt för scenariostyrda stateändringar, flaggor, metrics, injects och loggrader.
- Den faktiska generiska turn-motorn finns i [rules_engine.py](../../src/services/rules_engine.py), medan scenariobunden domänlogik i första hand bör ligga i scenariot.

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

### `original_text`

Valfri ursprungstext från scenarioförfattaren.

Fältet är tänkt för scenario som först skrivs i fri text eller markdown och
sedan översätts till JSON. Det används inte dynamiskt av scenariomotorn, men
gör det möjligt att spara källmaterialet tillsammans med det validerade
scenariot.

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

## `states`

`states` är den ordnade listan över scenariots definierade state-lägen. Första posten är alltid startläget som backend använder när en session skapas.

Ett scenario kan alltså beskriva en tänkt statekedja som:

- `initial-detection`
- `escalation`
- `containment`
- `recovery`

Varje state måste ha:

- `id`: stabilt unikt state-id
- `phase`: maskinläsbart fas-id
- `title`: kort visningsnamn
- `description`: vad state-läget betyder i scenariot

Första state-posten, `states[0]`, måste dessutom ha:

- `time`
- `impact_level`
- `narration`

Övriga states kan vara:

- kompletta states med full state-data
- lätta states med bara metadata och eventuellt narrativ

### `time`

Tid för state-läget. Rekommenderat format är `HH:MM`.

Detta krävs för `states[0]` och är valfritt för senare states.

### `phase`

Maskinläsbart namn på state-läget.

Rekommenderad skrivregel:

- använd ett kort, stabilt, maskinläsbart fas-id
- använd små bokstäver och bindestreck

Bra exempel:

- `initial-detection`
- `escalation`
- `containment`
- `recovery`

Viktigt:

- alla `phase`-värden i `states` måste vara unika
- alla `set_phase`-effekter i `executable_rules` måste peka på en `phase` som finns i `states`

### `known_facts`

Det deltagarna vet i detta state-läge.

### `unknowns`

Det deltagarna ännu inte vet men behöver utreda i detta state-läge.

### `affected_systems`

System eller tjänster som bedöms vara påverkade i detta state-läge.

### `business_impact`

Hur verksamheten påverkas i detta state-läge.

### `impact_level`

Övergripande påverkan i state-läget på en femgradig skala.

Rekommenderad tolkning:

- `1`: mycket begränsad påverkan, mest lokal störning
- `2`: märkbar påverkan men inom ett begränsat område
- `3`: tydlig påverkan på flera funktioner eller verksamhetsdelar
- `4`: allvarlig påverkan på kritiska verksamheter, hög tidspress
- `5`: extrem påverkan, långvarig eller samhällskritisk störning

### `narration`

Fördefinierat narrativ för detta state-läge.

För `states[0]` används detta som initial lägesbild när sessionen startas.

Struktur:

- `default`: gemensamt narrativ för alla målgrupper
- `by_audience`: valfria målgruppsspecifika narrativ

Prioritetsregel:

- backend använder först `by_audience` för vald målgrupp om den finns
- annars används `default`

Varje narrativ följer samma struktur som en vanlig narration i API:t:

- `situation_update`
- `key_points`
- `new_consequences`
- `injects`
- `decisions_to_consider`
- `facilitator_notes`

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

## `text_matchers`

`text_matchers` beskriver enkla, scenariodefinierade textmatchningar mot rå deltagartext.

Tanken är att scenariot ska kunna säga att vissa ord eller fraser bör komplettera den strukturerade tolkningen, till exempel att `extern åtkomst` bör leda till target `external_access`.

De används dynamiskt efter LLM-tolkningen och före regelmotorn. Matchningen är additiv: den kompletterar den redan tolkade actionn i stället för att skriva över den.

Varje textmatcher innehåller:

- `id`
- `field`
- `match_type`
- `patterns`
- `value`

### `field`

Tillåtna värden i v1:

- `action.action_types`
- `action.targets`

### `match_type`

Tillåtna värden i v1:

- `contains_any`
- `contains_all`

### `patterns`

Lista med textmönster som ska jämföras mot rå deltagartext.

Rekommendation:

- använd korta, konkreta uttryck
- skriv flera vanliga varianter om ni vet att deltagare uttrycker sig olika
- håll dem scenario- och domänspecifika

### `value`

Det värde som ska adderas till fältet när matchningen träffar.

Exempel:

```json
{
  "id": "matcher-external-access",
  "field": "action.targets",
  "match_type": "contains_any",
  "patterns": ["extern åtkomst", "extern access", "vpn"],
  "value": "external_access"
}
```

## `target_aliases`

`target_aliases` beskriver scenariodefinierade alias för target-normalisering.

De används dynamiskt för att lägga till kanoniska target-värden utifrån:

- redan tolkade provider-targets
- rå deltagartext

Det här är lämpligt när LLM:n returnerar mänskliga labels som `Externa anslutningar`, men scenarioreglerna behöver arbeta mot ett stabilt värde som `external_access`.

Exempel:

```json
{
  "id": "alias-external-access",
  "canonical": "external_access",
  "aliases": ["extern åtkomst", "externa anslutningar", "vpn"]
}
```

Normaliseringen är additiv:

- originaltarget får finnas kvar
- det kanoniska värdet läggs till om det saknas
- övningsloggen kan visa vilken aliasregel som användes

Rekommendation:

- använd `target_aliases` för synonymhantering och normalisering
- använd `text_matchers` för enkel textdriven komplettering av `action_types` eller `targets`
- använd `interpretation_hints` när normaliseringen också ska bero på kontext, till exempel redan tolkade `action_types`

## `interpretation_hints`

`interpretation_hints` beskriver deklarativa tolkhints som kan komplettera LLM-tolkningen med ytterligare `action_types` eller `targets`.

Tanken är att scenariot ska kunna uttrycka att:

- viss råtext i kombination med en redan tolkad åtgärdstyp bör ge extra targets
- vissa kombinationer av action types och targets bör förstärkas deterministiskt

De används dynamiskt efter `text_matchers` och före regelmotorn. Hints är additiva och används för att komplettera `action_types` eller `targets`, inte för att skriva över befintlig tolkning.

Varje hint innehåller:

- `id`
- `when`
- `add_action_types` eller `add_targets`
- valfritt `confidence_boost`

### `when`

`when` måste innehålla minst ett villkor i v1:

- `text_contains_any`
- `action_types_contains`
- `targets_contains`

### `add_action_types`

Action types som ska läggas till om hinton träffar.

### `add_targets`

Targets som ska läggas till om hinton träffar.

### `confidence_boost`

Valfritt metadatafält för framtida bruk. Det finns med i modellen nu, men används ännu inte dynamiskt.

Exempel:

```json
{
  "id": "hint-containment-external-access",
  "when": {
    "action_types_contains": ["containment"],
    "text_contains_any": ["extern åtkomst", "vpn"]
  },
  "add_targets": ["external_access"]
}
```

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
- `state.no_communication_turns`
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
2. lägg till ett state i `states`
3. placera det först i listan om det är startläget
4. använd samma fasnamn konsekvent i scenario, dokumentation och regler
5. lägg till en `set_phase`-effekt i `executable_rules` när en senare fas ska aktiveras

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
