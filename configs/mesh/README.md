# configs/mesh — unused

Каталог **не runtime**. Mesh Wi-Fi / provisioning здесь не внедрён: `mesh_topology.yaml` держит `nodes: []`, файлы — archive-заготовка.

Не предлагать mesh как рабочий транспорт узлов. Канон связи ESP32 ↔ backend = MQTT (см. `doc_ai/03_TRANSPORT_MQTT/`).
