# tesina-cs-computacion

## Etapa 1: archivos base y demanda reproducible

La red estática se conserva en `code/networks/synthetic/grid5x5.net.xml`. Los
parámetros de demanda están en
[`code/config/base_files.json`](code/config/base_files.json). Para generar la
matriz de demandas se necesita SUMO (`SUMO_HOME`) y se ejecuta:

```bash
python code/generate_base_files/main.py \
  --config code/config/base_files.json
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
  --config code/config/base_files.json
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