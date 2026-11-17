# tesina-cs-computacion

## Etapa 1: archivos base y demanda reproducible

La red estática se conserva en `code/networks/synthetic/grid5x5.net.xml`. Los
parámetros de demanda están en
[`code/generate_base_files/config/base_files.json`](code/generate_base_files/config/base_files.json). Para generar la
matriz de demandas se necesita SUMO (`SUMO_HOME`) y se ejecuta:

```bash
python code/generate_base_files/main.py \
  --config code/generate_base_files/config/base_files.json
```

El proceso valida que la red tenga aristas externas con carriles, usa la
semilla tanto para `randomTrips.py` como para `duarouter`, y asigna exactamente
`round(n * cav_penetration)` vehículos como CAV. Los archivos se guardan junto a
la red, en una carpeta `routes/<nombre-de-configuracion>/`, y el único
manifiesto de cada configuración es
`routes/<nombre-de-configuracion>/manifest.json`. Separar las configuraciones
en carpetas evita sobrescribir rutas o manifiestos al utilizar más de un
archivo JSON para la misma red.

Para generar toda la matriz configurada de archivos base (una combinación por
cada semilla y tasa CAV), ejecutar:

```bash
python code/generate_base_files/main.py \
  --config code/generate_base_files/config/base_files.json
```

La estructura resultante es:

```text
code/networks/synthetic/
├── grid5x5.net.xml
└── routes/
    └── base_files/
        ├── seed42_cav00.rou.xml
        ├── seed42_cav25.rou.xml
        ├── ...
        └── manifest.json
```

## Etapa 2: generación offline de artefactos

La Etapa 2 se ejecuta con una configuración independiente de los archivos
base:
[`code/generate_offline_artifacts/config/offline_artifacts.json`](code/generate_offline_artifacts/config/offline_artifacts.json).
Esta configuración referencia la red y una carpeta de rutas producida por la
Etapa 1 mediante su `manifest.json`, y define una lista de experimentos. Cada
experimento referencia un único escenario base y puede definir sus propios
parámetros de simulación, incidente, detectores y subgrafo. La red
correspondiente se obtiene de la entrada del manifiesto; no se repite en esta
configuración.

```bash
python code/generate_offline_artifacts/main.py \
  --config code/generate_offline_artifacts/config/offline_artifacts.json
```

Todos los experimentos se almacenan en una carpeta común. Cada experimento
contiene:

```text
experiments/<experimento>/
├── manifest.json
├── <experimento>.sumocfg
├── artifacts/
│   ├── graph.graphml
│   ├── subgraph.graphml
│   └── detectors.add.xml
```

La carpeta común se configura mediante `output_directory`. La Etapa 2 crea
únicamente los artefactos necesarios para las etapas siguientes. Las salidas de
simulación, métricas y resultados comparativos se crearán en sus respectivas
etapas. No se genera un manifiesto global: cada experimento tiene su propio
`manifest.json`. La etapa reutiliza la demanda concreta del escenario para
ponderar el grafo dual y conserva los parámetros del incidente en el manifiesto.

El `.sumocfg` referencia el `.net.xml` y el `.rou.xml` resueltos desde el
manifiesto de archivos base, además de los detectores E2 generados. Los
parámetros del incidente se mantienen para que la Etapa 3 los aplique mediante
TraCI y `IncidentManager`.

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
SUMO_BINARY=sumo-gui PYTHONPATH=code python -m simulation.simulator \
  --manifest experiments/incident_a2b2/manifest.json \
  --strategy m0

# Marcar el incidente y mostrar la ocupación
SUMO_BINARY=sumo-gui PYTHONPATH=code python -m simulation.simulator \
  --manifest experiments/incident_a2b2/manifest.json \
  --strategy m0 \
  --gui-overlay
```

Con `SUMO_BINARY=sumo` no se abre ninguna ventana y la simulación es apta para
ejecuciones batch o sin entorno gráfico.

## Etapa 3: ejecución de simulaciones

La simulación recibe el manifiesto de un experimento generado por la Etapa 2
y una estrategia (`m0` a `m3`):

```bash
cd code
python3 -m simulation.simulator \
  --manifest ../experiments/incident_a2b2/manifest.json \
  --strategy m0
```

La ejecución lee del manifiesto el `.sumocfg`, la configuración del incidente
y los directorios del experimento. Las salidas crudas se guardan en
`output/<estrategia>/`. El cálculo de métricas pertenece a una etapa posterior
y no se ejecuta durante esta etapa.

## Etapa 4: extracción y procesamiento de métricas

La Etapa 4 lee el manifiesto del experimento y procesa las salidas crudas de
las estrategias configuradas. La configuración y los módulos de esta etapa se
encuentran en [`code/metrics/`](code/metrics/), con la configuración en
[`code/metrics/config/metrics.json`](code/metrics/config/metrics.json).
El grafo se toma desde `artifacts/graph.graphml`, mientras que los archivos
`tripinfo.xml`, `fcd_output.xml` y `e2_output.xml` se leen desde
`output/<estrategia>/`.

```bash
python code/metrics/main.py \
  --config code/metrics/config/metrics.json
```

Los resultados se guardan por estrategia en:

```text
<experimento>/metrics/
├── m0/
│   ├── metrics.json
│   ├── metrics_stability_by_step.csv
│   └── metrics_congestion_<zona>_by_interval.csv
└── ...
```

Si una estrategia todavía no tiene sus salidas crudas, la etapa falla
explícitamente y no genera resultados incompletos. Las métricas no se calculan
durante la Etapa 3.

## Etapa 5: visualización y exportación de métricas

La Etapa 5 genera visualizaciones comparables para una o más estrategias (`m0`,
`m1`, etc.) a partir de los archivos exportados por la Etapa 4. La configuración
de ejemplo está en
[`code/metrics/config/visualization.json`](code/metrics/config/visualization.json):

```bash
python code/metrics/visualization/main.py \
  --config code/metrics/config/visualization.json
```

También se puede ejecutar como módulo desde `code`:

```bash
python -m metrics.visualization \
  --config metrics/config/visualization.json
```

La lista opcional `strategies` define las carpetas que se comparan. Si se omite,
se detectan automáticamente todas las estrategias que contienen un
`metrics.json`. Si no se especifica `formats`, se generan imágenes PNG.
También se pueden solicitar `svg` y `pdf`. `plots` acepta `summary`,
`stability` y `congestion`. Además de las imágenes individuales, siempre se
genera un único `report.html` autocontenido con todos los gráficos embebidos.
Las figuras, el reporte y un manifiesto de exportación se guardan en
`output_directory`.

When the experiment `manifest.json` is next to the metrics directory, the
visualization automatically reads `incident.begin_s` and `incident.end_s`.
Stability and congestion plots then shade the pre-incident, incident, and
post-incident stages and draw boundary lines. If no manifest is available, the
boundaries can be supplied explicitly with `incident_start_s` and
`incident_end_s` in the visualization configuration.
