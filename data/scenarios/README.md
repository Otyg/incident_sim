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
- presentationsriktlinjer per målgrupp

Det är viktigt att skilja på:

- validering: vad som faktiskt kontrolleras av Pydantic och JSON Schema
- författningskonvention: hur fälten bör användas för att bli begripliga och konsekventa
- exekvering: vad backend faktiskt använder dynamiskt under körning

## Viktigt om nuvarande implementation

Alla scenariofält valideras och lagras, men backend exekverar inte alla delar dynamiskt idag.

Nuvarande läge:

- `initial_state.phase` lagras och visas, men styr inte någon automatisk fasmaskin i backend.
- `inject_catalog[].trigger_conditions` är dokumentation för när injectet är tänkt att användas. De utvärderas inte generiskt av backend.
- `rules[]` beskriver scenariots tänkta orsak-verkan-samband, men backend läser idag inte in och kör dessa regler generiskt från scenariot.
- Den faktiska deterministiska regelmotorn finns i [rules_engine.py](../../src/services/rules_engine.py).

Det betyder att scenarioförfattaren redan nu kan dokumentera faser, triggers och regler tydligt, men att nya dynamiska beteenden också kräver kodändringar i backend om de ska verkställas automatiskt.

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

Regler beskriver scenariots tänkta logik, men körs inte generiskt från JSON idag.

Använd dem därför som:

- dokumentation för scenarioförfattare
- underlag för framtida automation
- stöd för facilitatorn

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

Faser är idag fria strängar. För att göra dem begripliga och framtidssäkra:

1. välj ett kort fas-id i kebab-case
2. använd samma fasnamn konsekvent i scenario, dokumentation och eventuell framtida logik
3. låt varje fas representera ett tydligt övningsläge eller beslutsläge

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

Triggers bör beskriva när facilitatorn bör använda ett inject eller när en regel borde slå till.

Bra arbetsmodell:

1. skriv triggern utifrån något observerbart
2. koppla den till ett mätbart eller tydligt tillstånd
3. håll texten kort och enhetlig

Bra exempel:

- `media_pressure når 2`
- `ingen extern kommunikation efter två turns`
- `service_disruption ökar efter containment-beslut`

## Hur du lägger till regler

Eftersom reglerna inte exekveras generiskt än bör de skrivas som dokumenterad designintention.

Bra arbetsmodell:

1. beskriv vad som triggar regeln
2. beskriv vad facilitatorn eller framtida backend borde göra som följd
3. använd samma ord i `conditions`, `effects`, `trigger_conditions` och övriga scenariot

Om du vill att en ny regel faktiskt ska påverka körningen automatiskt idag behöver du även uppdatera [rules_engine.py](../../src/services/rules_engine.py).

## Validering

Scenarion valideras i applikationen av Pydantic-modellen `Scenario`.

För extern validering kan du använda:

- JSON Schema-filen [scenario.schema.json](scenario.schema.json)
- uppladdning via UI eller POST till `/scenarios`

## Exempel

Se exempelscenariot i [municipality_ransomware.json](municipality_ransomware.json).
