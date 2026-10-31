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
<red>/experiments/<experimento>/
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