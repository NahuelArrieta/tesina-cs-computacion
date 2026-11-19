# tesina-cs-computacion

## Configuración local

Copiar [`.env.sample`](.env.sample) a `.env` y ajustar las rutas de SUMO y los
directorios del proyecto. Los valores se pueden cargar desde una sesión shell:

```bash
cp .env.sample .env
set -a
. ./.env
set +a
```

El archivo `.env` está excluido de Git. `.env.sample` contiene los valores
predeterminados del proyecto.

## Etapa 1: archivos base y demanda reproducible

La Etapa 1 recibe únicamente el nombre de un experimento y lee su configuración
desde `EXPERIMENT_DIR/<nombre>/manifest.json`. Genera una ruta `.rou.xml` por
cada tasa de penetración CAV configurada, a partir de una única ruta neutral,
y no crea ningún archivo JSON de salida.

```bash
EXPERIMENT_DIR="$PWD/experiments" \
NETWORK_DIR="$PWD/source files/networks" \
VTYPE_DIR="$PWD/source files/car distribution" \
python code/generate_base_files/main.py sample
```

Si `EXPERIMENT_DIR` no está definido, se utiliza `<raíz-del-repositorio>/experiments`.
Los directorios predeterminados son:

- Red: `NETWORK_DIR/<network>`
- Tipos de vehículo: `VTYPE_DIR/<vtypes>`
- Rutas: `EXPERIMENT_DIR/<experimento>/routes`

El manifiesto de ejemplo es:

```json
{
  "experiment": "sample",
  "network": "grid5x5.net.xml",
  "vtypes": "vtypes.add.xml",
  "begin_s": 0,
  "end_s": 3600,
  "period_s": 1.5,
  "routes_seed": 42,
  "cav_penetrations": [0.0, 0.25, 0.5, 0.75, 1.0]
}
```

- `network` y `vtypes` contienen solo nombres de archivo.
- `begin_s`, `end_s` y `period_s` controlan la demanda de `randomTrips.py`.
- `routes_seed` se usa para `randomTrips.py`, `duarouter` y la selección
  reproducible de CAV y distribuciones HDV.
- `cav_penetrations` puede contener tasas entre `0.0` y `1.0`.

El proceso genera primero `routes.rou.xml`, sin atributos `type` ni definiciones
vType, con una definición nombrada por cada ruta única. Después genera una
archivo por penetración que contiene solamente vTypes y vehículos con
`route="<route_id>"`. Cada penetración asigna exactamente
`round(n * cav_penetration)` vehículos CAV. Las distribuciones humanas se leen
directamente del archivo `.add.xml` indicado por `vtypes`. Los archivos de
penetración no repiten las listas de aristas de las rutas.

Al ejecutar SUMO, ambos archivos se pasan como rutas:

```text
--route-files routes.rou.xml,penetration_25.rou.xml
```

La estructura resultante es:

```text
experiments/sample/routes/
├── routes.rou.xml
├── penetration_0.rou.xml
├── penetration_25.rou.xml
├── penetration_50.rou.xml
├── penetration_75.rou.xml
└── penetration_100.rou.xml
```

`code/tools/generate_vtypes.py` contiene una utilidad independiente para
generar el archivo `.add.xml` de distribuciones humanas usado por la Etapa 1.
No genera ni modifica los `.rou.xml`.

```bash
python code/tools/generate_vtypes.py \
  code/dataset_analysis/pNeuma/sumo_params.csv \
  "source files/car distribution/vtypes.add.xml" \
  --vehicle-type "Car=100" \
  --seed 42
```

El resultado incluye 50 muestras por distribución y guarda reproduciblemente,
dentro de un comentario XML, la herramienta que lo creó, la seed, el CSV de
entrada y los porcentajes de tipos solicitados.

Internamente, Stage 1 está dividido en dos módulos:

- [`code/generate_base_files/generate_routes.py`](code/generate_base_files/generate_routes.py)
  genera la red de rutas compartida y valida las aristas.
- [`code/generate_base_files/generate_penetrations.py`](code/generate_base_files/generate_penetrations.py)
  asigna CAV/HDV y genera un archivo por tasa de penetración.

## Etapa 2: generación offline de artefactos

La Etapa 2 recibe únicamente el nombre del experimento y lee todos los valores
desde `EXPERIMENT_DIR/<nombre>/manifest.json`. La red se resuelve desde
`NETWORK_DIR/<network>` y las rutas desde
`EXPERIMENT_DIR/<nombre>/routes/`.

```bash
EXPERIMENT_DIR="$PWD/experiments" \
NETWORK_DIR="$PWD/source files/networks" \
python code/generate_offline_artifacts/main.py sample
```

Los campos adicionales del manifiesto son `incident`, `detectors` y `subgraph`.
Los valores raíz `begin_s` y `end_s` definen también la ventana temporal de la
simulación; no se mantiene un bloque `simulation` duplicado. La Etapa 2 genera
los artefactos generales una sola vez y valida
que exista el archivo de rutas de cada tasa de penetración:

```text
experiments/<experimento>/
├── routes/
│   ├── routes.rou.xml
│   └── penetration_<rate>.rou.xml
├── artifacts/
│   ├── graph.graphml
│   ├── subgraph.graphml
│   └── detectors.add.xml
```

`graph.graphml`, `subgraph.graphml` y `detectors.add.xml` son generales al
experimento. Esta etapa no genera archivos `.sumocfg` ni un manifiesto de salida.

Los parámetros del incidente se mantienen en el manifiesto para que la Etapa 3
los aplique mediante TraCI y `IncidentManager`.

El incidente no se genera como un archivo adicional de SUMO. Durante la
simulación se crea y controla dinámicamente mediante
[`IncidentManager`](code/simulation/incident_manager.py), que agrega el
vehículo-obstrucción por TraCI, inicia la obstrucción y libera el carril al
finalizar el intervalo configurado.

Con `SUMO_BINARY=sumo-gui`, la simulación puede mostrar el subgrafo upstream
directamente sobre las calles reales de SUMO-GUI. Cada calle se colorea según
la ocupación `vehículos / capacidad_de_la_arista` (verde: vacía; rojo: sobre
su capacidad). La calle del incidente se marca siempre con un círculo rojo.
El ancho del overlay representa el mayor turn ratio saliente de la calle. La
frecuencia de actualización se puede configurar con
`simulation.visualization_interval_s` y por defecto es de 10 segundos.

La visualización se puede desactivar para ejecuciones batch o sin entorno
gráfico con `"visualization": false` dentro de `simulation`. El monitor usa
suscripciones TraCI para consultar las cantidades de vehículos y mantiene una
única fuente de mediciones para dos backends:

- Con `SUMO_BINARY=sumo-gui`, colorea las aristas reales de SUMO-GUI mediante
  overlays sobre la geometría de cada calle. Los detectores E2 se definen con
  `show="false"` de forma permanente: no se dibujan, pero siguen activos y
  escriben `e2_output.xml`. La calle del incidente se marca siempre con un
  círculo rojo, incluso si no se usa `--gui-overlay`.
La visualización se activa solamente en SUMO-GUI. Se puede seleccionar si se
muestran únicamente el incidente o también el estado de ocupación:

```bash
# Solo marcar el incidente
SUMO_BINARY=sumo-gui PYTHONPATH=code python -m simulation.main \
  incident_a2b2 \
  --strategy m0

# Marcar el incidente y mostrar la ocupación
SUMO_BINARY=sumo-gui PYTHONPATH=code python -m simulation.main \
  incident_a2b2 \
  --strategy m0 \
  --gui-overlay
```

Con `SUMO_BINARY=sumo` no se abre ninguna ventana y la simulación es apta para
ejecuciones batch o sin entorno gráfico.

## Etapa 3: ejecución de simulaciones

La Etapa 3 recibe únicamente el nombre del experimento. Construye una
configuración SUMO temporal a partir del manifiesto, la red, las rutas y los
detectores; no genera ningún archivo `.sumocfg` persistente. La penetración
utilizada se selecciona desde `cav_penetrations` en el manifiesto.
La resolución temporal de SUMO es común a todos los experimentos y está
definida por `DEFAULT_STEP_LENGTH_S = 0.1` en
[`code/simulation/simulator.py`](code/simulation/simulator.py).

```bash
PYTHONPATH=code python -m simulation.main sample
```

Sin flags se ejecutan todas las combinaciones de penetración y estrategia.
Para ejecutar una sola estrategia en todas las penetraciones:

```bash
PYTHONPATH=code python -m simulation.main sample --strategy m0
```

Para ejecutar una única penetración:

```bash
PYTHONPATH=code python -m simulation.main sample --penetration 0.25
```

El manifiesto define las seeds de simulación en `simulation_seeds`. Sin
`--seed` se ejecutan todas; con esa flag se ejecuta únicamente la seed indicada.
La salida queda ordenada como
`output/p{penetración}/m{estrategia}/seed_{seed}/`, por ejemplo
`output/p25/m1/seed_1/`.
La estrategia `m0` es la línea base sin CAV y se ejecuta una única vez en
`output/p0/m0/`. Las estrategias `m1`, `m2` y `m3` se ejecutan únicamente para
penetraciones mayores que cero. Por eso `--penetration 0` no está permitido.
La ejecución es secuencial por defecto. Para ejecutar simulaciones en procesos
independientes se puede indicar un límite de workers:

```bash
PYTHONPATH=code python -m simulation.main sample --workers 4
```

Cada proceso tiene su propia conexión TraCI y su propio proceso SUMO. No se
debe combinar `--workers` mayor que uno con `--gui-overlay`.

La ejecución lee del manifiesto la configuración del incidente y los directorios
del experimento. Las salidas crudas se guardan por penetración y estrategia.
El cálculo de métricas pertenece a una etapa posterior y no se ejecuta durante
esta etapa.

## Etapa 4: extracción y procesamiento de métricas

La Etapa 4 lee el manifiesto del experimento y procesa las salidas crudas de
las estrategias configuradas. La configuración y los módulos de esta etapa se
encuentran en [`code/metrics/`](code/metrics/), con la configuración en
[`code/metrics/config/metrics.json`](code/metrics/config/metrics.json).
El grafo se toma desde `artifacts/graph.graphml`, mientras que los archivos
`tripinfo.xml`, `fcd_output.xml` y `e2_output.xml` se leen desde
`output/p{penetración}/m{estrategia}/`.

```bash
python code/metrics/main.py \
  --config code/metrics/config/metrics.json
```

Los resultados se guardan por estrategia en:

```text
<experimento>/metrics/p<penetración>/m<estrategia>/
├── metrics.json
├── metrics_stability_by_step.csv
└── metrics_congestion_<zona>_by_interval.csv
```

Si una estrategia todavía no tiene sus salidas crudas, la etapa falla
explícitamente y no genera resultados incompletos. Las métricas no se calculan
durante la Etapa 3.

## Etapa 5: visualización y exportación de métricas

La Etapa 5 genera visualizaciones SVG comparables para el experimento a partir
de los resultados agregados por la Etapa 4:

```bash
PYTHONPATH=code python -m metrics.visualization.main sample
```

Los resultados se guardan únicamente en formato SVG:

```text
experiments/<experimento>/results/
├── report.html
└── graphics/
    └── <nombre>.svg
```

El reporte HTML referencia los gráficos SVG. No se generan PNG, PDF, CSV ni
manifiestos de visualización.
