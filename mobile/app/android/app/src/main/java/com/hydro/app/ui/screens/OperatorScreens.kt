package com.hydro.app.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hydro.app.core.domain.Alert
import com.hydro.app.core.domain.Greenhouse
import com.hydro.app.core.domain.Node
import com.hydro.app.core.domain.StatusTone
import com.hydro.app.core.domain.Zone
import com.hydro.app.core.domain.levelReading
import com.hydro.app.core.domain.statusTone
import com.hydro.app.features.operator.NodeOperatorViewModel
import com.hydro.app.features.operator.OperatorAlertsViewModel
import com.hydro.app.features.operator.OverviewViewModel
import com.hydro.app.features.operator.ZoneListViewModel
import com.hydro.app.features.operator.ZoneOperatorViewModel
import com.hydro.app.ui.components.ConfirmActionDialog
import com.hydro.app.ui.components.SectionHeader
import com.hydro.app.ui.components.StatusChip
import com.hydro.app.ui.components.TelemetryTile
import com.hydro.app.ui.components.formatMetric

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GreenhousesScreen(
    onOpenZones: (Int) -> Unit,
    onOpenAlerts: () -> Unit,
    onOpenSettings: () -> Unit,
    onProvisioning: () -> Unit,
    onLogout: () -> Unit,
    vm: OverviewViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    LaunchedEffect(Unit) { vm.start() }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Теплицы") },
                actions = {
                    IconButton(onClick = vm::refresh) {
                        Icon(Icons.Default.Refresh, contentDescription = "Обновить")
                    }
                    IconButton(onClick = onOpenSettings) {
                        Icon(Icons.Default.Settings, contentDescription = "Сервер")
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Text("Сервер ${state.serverLabel}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                TextButton(onClick = onOpenAlerts) {
                    Text("Активные алерты: ${state.activeAlerts}")
                }
            }
            if (state.loading) {
                item { CircularProgressIndicator() }
            }
            state.error?.let { message -> item { Text(message, color = MaterialTheme.colorScheme.error) } }
            if (!state.loading && state.greenhouses.isEmpty() && state.error == null) {
                item { Text("Теплиц нет. Проверьте учётную запись и доступ к зонам.") }
            }
            items(state.greenhouses, key = { it.id }) { greenhouse ->
                GreenhouseCard(greenhouse, onClick = { onOpenZones(greenhouse.id) })
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onProvisioning) { Text("Provisioning") }
                    OutlinedButton(onClick = onLogout) { Text("Выйти") }
                }
            }
        }
    }
}

@Composable
private fun GreenhouseCard(greenhouse: Greenhouse, onClick: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(greenhouse.name.ifBlank { "Теплица ${greenhouse.id}" }, style = MaterialTheme.typography.titleLarge)
            Text(
                listOfNotNull(greenhouse.uid.takeIf { it.isNotBlank() }, greenhouse.timezone, greenhouse.description)
                    .joinToString(" · ")
                    .ifBlank { "Без описания" },
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ZonesScreen(
    greenhouseId: Int,
    onOpenZone: (Int) -> Unit,
    onBack: () -> Unit,
    vm: ZoneListViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    LaunchedEffect(greenhouseId) { vm.start(greenhouseId) }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(state.title) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад")
                    }
                },
                actions = {
                    IconButton(onClick = vm::refresh) {
                        Icon(Icons.Default.Refresh, contentDescription = "Обновить")
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (state.loading) item { CircularProgressIndicator() }
            state.error?.let { message -> item { Text(message, color = MaterialTheme.colorScheme.error) } }
            if (!state.loading && state.zones.isEmpty()) item { Text("В этой теплице нет зон.") }
            items(state.zones, key = { it.id }) { zone ->
                ZoneCard(zone, onClick = { onOpenZone(zone.id) })
            }
        }
    }
}

@Composable
private fun ZoneCard(zone: Zone, onClick: () -> Unit) {
    val tone = statusTone(zone.healthStatus ?: zone.status)
    Card(modifier = Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text(zone.name.ifBlank { "Зона ${zone.id}" }, style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                StatusChip(zone.status ?: zone.healthStatus ?: "—", tone)
            }
            Text(
                listOfNotNull(
                    zone.controlMode?.let { "режим $it" },
                    zone.nodesCount?.let { "узлов $it" },
                    zone.waterState?.let { "вода $it" },
                ).joinToString(" · ").ifBlank { zone.uid },
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ZoneDetailsScreen(
    zoneId: Int,
    onOpenNode: (Int) -> Unit,
    onBack: () -> Unit,
    vm: ZoneOperatorViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    var irrigate by remember { mutableStateOf(false) }
    var estop by remember { mutableStateOf(false) }
    LaunchedEffect(zoneId) { vm.start(zoneId) }
    val mode = state.controlMode ?: state.zone?.controlMode
    val manual = mode.equals("manual", ignoreCase = true)
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(state.zone?.name ?: "Зона $zoneId") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад")
                    }
                },
                actions = {
                    IconButton(onClick = vm::refresh) {
                        Icon(Icons.Default.Refresh, contentDescription = "Обновить")
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (state.loading && state.zone == null) item { CircularProgressIndicator() }
            state.error?.let { message -> item { Text(message, color = MaterialTheme.colorScheme.error) } }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    StatusChip(state.zone?.status ?: "статус", statusTone(state.zone?.status))
                    StatusChip(mode ?: "режим", if (manual) StatusTone.Warning else statusTone(mode))
                }
                state.stage?.let { Text("Стадия: $it", modifier = Modifier.padding(top = 8.dp)) }
                state.controlModeNote?.let {
                    Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 4.dp))
                }
            }
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("E-STOP", fontWeight = FontWeight.Bold, color = if (manual) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface)
                        Text(
                            if (manual) {
                                "Зона в ручном режиме: автоматика не командует поливом. Физическая кнопка E-STOP на узле держит актуаторы выключенными. Отдельной REST-команды E-STOP backend не публикует."
                            } else {
                                "Физический E-STOP обрабатывает узел. С телефона аварийное действие — перевод control_mode в manual с указанием причины (роль operator)."
                            },
                        )
                    }
                }
            }
            item { SectionHeader("Телеметрия", state.telemetry?.lastUpdated) }
            item {
                val tel = state.telemetry
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TelemetryTile("pH", formatMetric(tel?.ph, 2), "pH", Modifier.weight(1f))
                        TelemetryTile("EC", formatMetric(tel?.ec, 2), "мСм/см", Modifier.weight(1f))
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TelemetryTile("Температура", formatMetric(tel?.airTemperature, 1), "°C", Modifier.weight(1f))
                        TelemetryTile("Влажность", formatMetric(tel?.airHumidityPercent, 0), "%", Modifier.weight(1f))
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TelemetryTile("CO₂", formatMetric(tel?.co2, 0), "ppm", Modifier.weight(1f))
                        TelemetryTile(
                            state.level?.label ?: "Уровень",
                            state.level?.valueText ?: "нет в снимке",
                            state.level?.metric ?: "не в zone snapshot",
                            Modifier.weight(1f),
                        )
                    }
                }
            }
            item {
                Button(onClick = { irrigate = true }, enabled = !state.busy, modifier = Modifier.fillMaxWidth()) {
                    Text("Принудительный полив")
                }
                OutlinedButton(
                    onClick = { estop = true },
                    enabled = !state.busy && !manual,
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                ) {
                    Text(if (manual) "Уже ручной режим" else "Аварийно в ручной режим")
                }
                state.message?.let { Text(it, modifier = Modifier.padding(top = 8.dp)) }
            }
            item { SectionHeader("Узлы", state.nodes.size.toString()) }
            if (state.nodes.isEmpty() && !state.loading) {
                item { Text("Узлы зоны не найдены.") }
            }
            items(state.nodes, key = { it.id }) { node ->
                NodeRow(node, onClick = { onOpenNode(node.id) })
            }
        }
    }
    if (irrigate) {
        ConfirmActionDialog(
            title = "Запустить полив?",
            body = "На зону уйдёт FORCE_IRRIGATION на 30 секунд. Команда проходит через Laravel в automation-engine.",
            confirmLabel = "Запустить",
            destructive = true,
            onDismiss = { irrigate = false },
            onConfirm = {
                irrigate = false
                vm.irrigate(30)
            },
        )
    }
    if (estop) {
        ConfirmActionDialog(
            title = "Аварийный перевод в manual",
            body = "Оператор может перевести зону из auto/semi в manual. Автоматика остановит управление. Причина обязательна.",
            confirmLabel = "Перевести",
            destructive = true,
            reasonLabel = "Причина",
            onDismiss = { estop = false },
            onConfirm = { reason ->
                estop = false
                vm.emergencyManual(reason)
            },
        )
    }
}

@Composable
private fun NodeRow(node: Node, onClick: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(node.name.ifBlank { node.uid }, fontWeight = FontWeight.SemiBold)
                Text("${node.type.ifBlank { "узел" }} · ${node.uid}", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            StatusChip(node.status ?: "—", statusTone(node.status))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NodeDetailsScreen(
    nodeId: Int,
    onBack: () -> Unit,
    vm: NodeOperatorViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    var restart by remember { mutableStateOf(false) }
    var relay by remember { mutableStateOf<Pair<String, Boolean>?>(null) }
    LaunchedEffect(nodeId) { vm.start(nodeId) }
    val level = levelReading(state.samples)
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(state.node?.name ?: "Узел $nodeId") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад")
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (state.loading && state.node == null) item { CircularProgressIndicator() }
            state.error?.let { message -> item { Text(message, color = MaterialTheme.colorScheme.error) } }
            item {
                val node = state.node
                Text("${node?.type.orEmpty()}  ${node?.uid.orEmpty()}")
                Text("Статус: ${node?.status ?: "—"} · lifecycle: ${node?.lifecycleState ?: "—"}")
                Text("Прошивка: ${node?.firmware ?: "—"} · RSSI: ${node?.rssi?.toString() ?: "—"}")
                Text("Был на связи: ${node?.lastSeenAt ?: "—"}")
                level?.let { Text("${it.label}: ${it.valueText} (${it.metric})") }
            }
            item { SectionHeader("Телеметрия узла") }
            if (state.samples.isEmpty() && !state.loading) {
                item { Text("Свежих значений нет.") }
            }
            items(state.samples) { sample ->
                Text("${sample.metricType ?: sample.channel ?: "метрика"}: ${formatMetric(sample.value, 2)}  ${sample.channel.orEmpty()}")
            }
            item {
                Button(onClick = { restart = true }, enabled = !state.busy, modifier = Modifier.fillMaxWidth()) {
                    Text("Перезапустить узел")
                }
                state.message?.let { Text(it, modifier = Modifier.padding(top = 8.dp)) }
            }
            if (state.actuators.isNotEmpty()) {
                item { SectionHeader("Актуаторы") }
            }
            items(state.actuators) { channel ->
                val name = channel.channel.orEmpty()
                Column {
                    Text(name, fontWeight = FontWeight.SemiBold)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { relay = name to true }, enabled = !state.busy) { Text("Включить") }
                        OutlinedButton(onClick = { relay = name to false }, enabled = !state.busy) { Text("Выключить") }
                    }
                }
            }
        }
    }
    if (restart) {
        ConfirmActionDialog(
            title = "Перезапустить узел?",
            body = "Уйдёт команда restart. Узел на короткое время пропадёт из сети.",
            confirmLabel = "Перезапустить",
            destructive = true,
            onDismiss = { restart = false },
            onConfirm = {
                restart = false
                vm.restart()
            },
        )
    }
    relay?.let { (channel, enabled) ->
        ConfirmActionDialog(
            title = if (enabled) "Включить $channel?" else "Выключить $channel?",
            body = "Команда set_relay уйдёт на узел через history-logger. Если узел в E-STOP, он удержит актуатор выключенным.",
            confirmLabel = if (enabled) "Включить" else "Выключить",
            destructive = true,
            onDismiss = { relay = null },
            onConfirm = {
                relay = null
                vm.setRelay(channel, enabled)
            },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AlertsScreen(
    onBack: () -> Unit,
    vm: OperatorAlertsViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    LaunchedEffect(Unit) { vm.start() }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Алерты") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад")
                    }
                },
                actions = {
                    IconButton(onClick = vm::refresh) {
                        Icon(Icons.Default.Refresh, contentDescription = "Обновить")
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item { Text("Показаны ACTIVE. Подтверждение вызывает PATCH /api/alerts/{id}/ack и переводит алерт в resolved.") }
            if (state.loading) item { CircularProgressIndicator() }
            state.error?.let { message -> item { Text(message, color = MaterialTheme.colorScheme.error) } }
            state.message?.let { message -> item { Text(message) } }
            if (!state.loading && state.alerts.isEmpty()) item { Text("Активных алертов нет.") }
            items(state.alerts, key = { it.id }) { alert ->
                AlertCard(alert, pending = state.pendingId == alert.id, onAck = { vm.acknowledge(alert.id) })
            }
        }
    }
}

@Composable
private fun AlertCard(alert: Alert, pending: Boolean, onAck: () -> Unit) {
    val tone = statusTone(alert.displayLevel)
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(alert.title ?: alert.code ?: alert.type, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                StatusChip(alert.displayLevel, tone)
            }
            Text(alert.displayMessage)
            Text(
                listOfNotNull(alert.displayZone, alert.nodeUid, alert.displayTime).joinToString(" · "),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (alert.isActive) {
                Button(onClick = onAck, enabled = !pending) {
                    Text(if (pending) "Подтверждение…" else "Подтвердить")
                }
            }
        }
    }
}
