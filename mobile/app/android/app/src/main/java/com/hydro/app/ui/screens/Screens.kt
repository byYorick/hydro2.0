@file:OptIn(ExperimentalMaterial3Api::class)

package com.hydro.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hydro.app.features.alerts.AlertsViewModel
import com.hydro.app.features.auth.presentation.LoginState
import com.hydro.app.features.auth.presentation.LoginViewModel
import com.hydro.app.features.greenhouses.GreenhousesViewModel
import com.hydro.app.features.provisioning.ProvisioningViewModel
import com.hydro.app.features.zones.ZoneDetailsViewModel
import com.hydro.app.features.zones.ZonesViewModel
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun LoginScreen(onLoggedIn: () -> Unit, vm: LoginViewModel = hiltViewModel()) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    val state = vm.state.collectAsState()
    
    LaunchedEffect(state.value) {
        if (state.value is LoginState.Success) onLoggedIn()
    }
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "Hydro 2.0",
            fontSize = 32.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp)
        )
        Text(
            text = "Система управления гидропоникой",
            fontSize = 16.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 32.dp)
        )
        
        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text("Email") },
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 16.dp),
            singleLine = true
        )
        
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("Пароль") },
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 24.dp),
            singleLine = true
        )
        
        when (val s = state.value) {
            is LoginState.Idle -> {
                Button(
                    onClick = { vm.login(email, password) },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = email.isNotBlank() && password.isNotBlank()
                ) {
                    Text("Войти")
                }
            }
            is LoginState.Loading -> {
                CircularProgressIndicator(modifier = Modifier.padding(16.dp))
            }
            is LoginState.Error -> {
                Text(
                    text = "Ошибка: ${s.message}",
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(bottom = 16.dp)
                )
                Button(
                    onClick = { vm.login(email, password) },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Повторить")
                }
            }
            is LoginState.Success -> {}
        }
    }
}

@Composable
fun GreenhousesScreen(
    onOpenZones: (Int) -> Unit,
    onOpenAlerts: () -> Unit,
    onProvisioning: () -> Unit,
    vm: GreenhousesViewModel = hiltViewModel()
) {
    val state = vm.state.collectAsState()
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Теплицы") },
                actions = {
                    IconButton(onClick = { vm.load() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Обновить")
                    }
                }
            )
        },
        floatingActionButton = {
            Row(
                modifier = Modifier.padding(8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                FloatingActionButton(
                    onClick = onOpenAlerts,
                    modifier = Modifier.size(48.dp)
                ) {
                    Text("!", fontSize = 20.sp)
                }
                FloatingActionButton(
                    onClick = onProvisioning,
                    modifier = Modifier.size(48.dp)
                ) {
                    Text("+", fontSize = 20.sp)
                }
            }
        }
    ) { padding ->
        if (state.value.isEmpty()) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                items(state.value) { gh ->
                    GreenhouseCard(
                        greenhouse = gh,
                        onClick = { onOpenZones(gh.id) }
                    )
                }
            }
        }
    }
}

@Composable
fun GreenhouseCard(
    greenhouse: com.hydro.app.core.domain.Greenhouse,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier.padding(16.dp)
        ) {
            Text(
                text = greenhouse.name,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold
            )
            if (greenhouse.location != null) {
                Text(
                    text = greenhouse.location,
                    fontSize = 14.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }
            Row(
                modifier = Modifier.padding(top = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                if (greenhouse.zonesCount != null) {
                    Text(
                        text = "Зон: ${greenhouse.zonesCount}",
                        fontSize = 14.sp
                    )
                }
                if (greenhouse.status != null) {
                    val statusColor = when (greenhouse.status.lowercase()) {
                        "ok" -> Color(0xFF4CAF50)
                        "warning" -> Color(0xFFFF9800)
                        "alert" -> Color(0xFFF44336)
                        else -> MaterialTheme.colorScheme.onSurfaceVariant
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .size(8.dp)
                                .clip(RoundedCornerShape(4.dp))
                                .background(statusColor)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(
                            text = greenhouse.status,
                            fontSize = 14.sp,
                            color = statusColor
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun ZonesScreen(
    greenhouseId: Int?,
    onOpenZone: (Int) -> Unit,
    onBack: () -> Unit,
    vm: ZonesViewModel = hiltViewModel()
) {
    val state = vm.state.collectAsState()
    
    LaunchedEffect(greenhouseId) {
        vm.load(greenhouseId)
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Зоны") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Назад")
                    }
                },
                actions = {
                    IconButton(onClick = { vm.load(greenhouseId) }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Обновить")
                    }
                }
            )
        }
    ) { padding ->
        if (state.value.isEmpty()) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                items(state.value) { zone ->
                    ZoneCard(
                        zone = zone,
                        onClick = { onOpenZone(zone.id) }
                    )
                }
            }
        }
    }
}

@Composable
fun ZoneCard(
    zone: com.hydro.app.core.domain.Zone,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier.padding(16.dp)
        ) {
            Text(
                text = zone.name,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold
            )
            if (zone.culture != null) {
                Text(
                    text = zone.culture,
                    fontSize = 14.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }
            if (zone.status != null) {
                val statusColor = when (zone.status.lowercase()) {
                    "ok" -> Color(0xFF4CAF50)
                    "warning" -> Color(0xFFFF9800)
                    "alert" -> Color(0xFFF44336)
                    else -> MaterialTheme.colorScheme.onSurfaceVariant
                }
                Row(
                    modifier = Modifier.padding(top = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(8.dp)
                            .clip(RoundedCornerShape(4.dp))
                            .background(statusColor)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = zone.status,
                        fontSize = 14.sp,
                        color = statusColor
                    )
                }
            }
        }
    }
}

@Composable
fun ZoneDetailsScreen(
    zoneId: Int,
    onBack: () -> Unit,
    vm: ZoneDetailsViewModel = hiltViewModel()
) {
    val zone = vm.zone.collectAsState()
    val telemetryLast = vm.telemetryLast.collectAsState()
    val telemetryHistory = vm.telemetryHistory.collectAsState()
    val commandState = vm.commandState.collectAsState()
    var selectedMetric by remember { mutableStateOf<String?>(null) }
    
    LaunchedEffect(zoneId) {
        vm.load(zoneId)
        vm.loadTelemetryLast(zoneId)
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(zone.value?.name ?: "Зона") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Назад")
                    }
                },
                actions = {
                    IconButton(onClick = { vm.loadTelemetryLast(zoneId) }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Обновить")
                    }
                }
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            item {
                // Current telemetry values
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp)
                    ) {
                        Text(
                            text = "Текущие значения",
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(bottom = 12.dp)
                        )
                        telemetryLast.value?.let { tel ->
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceEvenly
                            ) {
                                TelemetryValue("pH", tel.ph?.toString() ?: "-", "pH")
                                TelemetryValue("EC", tel.ec?.toString() ?: "-", "мСм/см")
                                TelemetryValue("Температура", tel.airTemp?.toString() ?: "-", "°C")
                                TelemetryValue("Влажность", tel.airHumidity?.toString() ?: "-", "%")
                            }
                        } ?: run {
                            CircularProgressIndicator(modifier = Modifier.align(Alignment.CenterHorizontally))
                        }
                    }
                }
            }
            
            item {
                // Charts section
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp)
                    ) {
                        Text(
                            text = "Графики",
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(bottom = 12.dp)
                        )
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            listOf("PH", "EC", "TEMP_AIR", "HUMIDITY_AIR").forEach { metric ->
                                FilterChip(
                                    selected = selectedMetric == metric,
                                    onClick = {
                                        selectedMetric = if (selectedMetric == metric) null else metric
                                        if (selectedMetric == metric) {
                                            vm.loadHistory(zoneId, metric)
                                        }
                                    },
                                    label = { Text(metric) },
                                    modifier = Modifier.padding(bottom = 8.dp)
                                )
                            }
                        }
                        selectedMetric?.let { metric ->
                            val history = telemetryHistory.value[metric] ?: emptyList()
                            if (history.isNotEmpty()) {
                                SimpleLineChart(
                                    data = history,
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .height(200.dp)
                                )
                            } else {
                                Text("Загрузка данных...", modifier = Modifier.padding(16.dp))
                            }
                        }
                    }
                }
            }
            
            item {
                // Commands section
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp)
                    ) {
                        Text(
                            text = "Команды",
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(bottom = 12.dp)
                        )
                        Button(
                            onClick = {
                                vm.sendCommand(zoneId, com.hydro.app.core.domain.CommandRequest("IRRIGATION_START"))
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text("Запустить полив")
                        }
                        when (val cmdState = commandState.value) {
                            is ZoneDetailsViewModel.CommandState.Loading -> {
                                CircularProgressIndicator(modifier = Modifier.padding(8.dp))
                            }
                            is ZoneDetailsViewModel.CommandState.Success -> {
                                Text(
                                    text = "Команда отправлена: ${cmdState.response.cmdId}",
                                    color = Color(0xFF4CAF50),
                                    modifier = Modifier.padding(8.dp)
                                )
                            }
                            is ZoneDetailsViewModel.CommandState.Error -> {
                                Text(
                                    text = "Ошибка: ${cmdState.message}",
                                    color = MaterialTheme.colorScheme.error,
                                    modifier = Modifier.padding(8.dp)
                                )
                            }
                            else -> {}
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun TelemetryValue(label: String, value: String, unit: String) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = label,
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = "$value $unit",
            fontSize = 18.sp,
            fontWeight = FontWeight.Bold
        )
    }
}

@Composable
fun SimpleLineChart(
    data: List<com.hydro.app.core.domain.TelemetryHistoryPoint>,
    modifier: Modifier = Modifier
) {
    com.hydro.app.ui.components.TelemetryChart(
        data = data,
        modifier = modifier
    )
}

@Composable
fun AlertsScreen(
    onBack: () -> Unit,
    vm: AlertsViewModel = hiltViewModel()
) {
    val state = vm.state.collectAsState()
    val acknowledgeState = vm.acknowledgeState.collectAsState()
    var filterStatus by remember { mutableStateOf<String?>(null) }
    
    LaunchedEffect(filterStatus) {
        vm.load(status = filterStatus)
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Алерты") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Назад")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            // Filters
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                FilterChip(
                    selected = filterStatus == null,
                    onClick = { filterStatus = null },
                    label = { Text("Все") }
                )
                FilterChip(
                    selected = filterStatus == "open",
                    onClick = { filterStatus = "open" },
                    label = { Text("Открытые") }
                )
                FilterChip(
                    selected = filterStatus == "acknowledged",
                    onClick = { filterStatus = "acknowledged" },
                    label = { Text("Подтвержденные") }
                )
            }
            
            if (state.value.isEmpty()) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Text("Нет алертов")
                }
            } else {
                LazyColumn(
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    items(state.value) { alert ->
                        AlertCard(
                            alert = alert,
                            onAcknowledge = {
                                vm.acknowledge(alert.id)
                            },
                            isAcknowledging = acknowledgeState.value is AlertsViewModel.AcknowledgeState.Loading
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun AlertCard(
    alert: com.hydro.app.core.domain.Alert,
    onAcknowledge: () -> Unit,
    isAcknowledging: Boolean
) {
    val levelColor = when (alert.level.lowercase()) {
        "critical" -> Color(0xFFF44336)
        "warning" -> Color(0xFFFF9800)
        "info" -> Color(0xFF2196F3)
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }
    
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (alert.status == "acknowledged") {
                MaterialTheme.colorScheme.surfaceVariant
            } else {
                MaterialTheme.colorScheme.surface
            }
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(12.dp)
                            .clip(RoundedCornerShape(6.dp))
                            .background(levelColor)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = alert.level.uppercase(),
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold,
                        color = levelColor
                    )
                }
                if (alert.status != "acknowledged") {
                    Button(
                        onClick = onAcknowledge,
                        enabled = !isAcknowledging,
                        modifier = Modifier.height(32.dp)
                    ) {
                        if (isAcknowledging) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                strokeWidth = 2.dp
                            )
                        } else {
                            Text("Подтвердить", fontSize = 12.sp)
                        }
                    }
                }
            }
            Text(
                text = alert.type,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(top = 8.dp)
            )
            Text(
                text = alert.message,
                fontSize = 14.sp,
                modifier = Modifier.padding(top = 4.dp)
            )
            if (alert.zoneName != null) {
                Text(
                    text = "Зона: ${alert.zoneName}",
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }
            Text(
                text = formatTimestamp(alert.timestamp),
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp)
            )
        }
    }
}

@Composable
fun ProvisioningScreen(
    onBack: () -> Unit,
    vm: ProvisioningViewModel = hiltViewModel()
) {
    val state = vm.state.collectAsState()
    var wifiSsid by remember { mutableStateOf("") }
    var wifiPassword by remember { mutableStateOf("") }
    var nodeName by remember { mutableStateOf("") }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Настройка узла") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Назад")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            when (val s = state.value) {
                is ProvisioningViewModel.ProvisioningState.Idle -> {
                    Button(
                        onClick = { vm.scanDevices() },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("Сканировать устройства")
                    }
                }
                is ProvisioningViewModel.ProvisioningState.Scanning -> {
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.CenterHorizontally))
                    Text("Поиск устройств...", modifier = Modifier.align(Alignment.CenterHorizontally))
                }
                is ProvisioningViewModel.ProvisioningState.FoundDevices -> {
                    Text("Найденные устройства:", fontSize = 18.sp, fontWeight = FontWeight.Bold)
                    s.devices.forEach { device ->
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    // Show configuration form
                                }
                        ) {
                            Text(
                                text = device.ssid,
                                modifier = Modifier.padding(16.dp)
                            )
                        }
                    }
                    Spacer(modifier = Modifier.height(16.dp))
                    OutlinedTextField(
                        value = wifiSsid,
                        onValueChange = { wifiSsid = it },
                        label = { Text("SSID Wi-Fi сети") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = wifiPassword,
                        onValueChange = { wifiPassword = it },
                        label = { Text("Пароль Wi-Fi") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = nodeName,
                        onValueChange = { nodeName = it },
                        label = { Text("Имя узла") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    if (s.devices.isNotEmpty()) {
                        Button(
                            onClick = {
                                vm.provisionDevice(
                                    s.devices.first(),
                                    ProvisioningViewModel.ProvisioningConfig(
                                        wifiSsid = wifiSsid,
                                        wifiPassword = wifiPassword,
                                        nodeName = nodeName
                                    )
                                )
                            },
                            modifier = Modifier.fillMaxWidth(),
                            enabled = wifiSsid.isNotBlank() && wifiPassword.isNotBlank() && nodeName.isNotBlank()
                        ) {
                            Text("Настроить узел")
                        }
                    }
                }
                is ProvisioningViewModel.ProvisioningState.Configuring -> {
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.CenterHorizontally))
                    Text("Настройка узла...", modifier = Modifier.align(Alignment.CenterHorizontally))
                }
                is ProvisioningViewModel.ProvisioningState.Success -> {
                    Text(
                        text = "Узел успешно настроен!",
                        color = Color(0xFF4CAF50),
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.align(Alignment.CenterHorizontally)
                    )
                }
                is ProvisioningViewModel.ProvisioningState.Error -> {
                    Text(
                        text = "Ошибка: ${s.message}",
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.align(Alignment.CenterHorizontally)
                    )
                    Button(
                        onClick = { vm.scanDevices() },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("Повторить")
                    }
                }
            }
        }
    }
}

fun formatTimestamp(timestamp: String): String {
    return try {
        val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.getDefault())
        val date = sdf.parse(timestamp)
        SimpleDateFormat("dd.MM.yyyy HH:mm", Locale.getDefault()).format(date ?: Date())
    } catch (e: Exception) {
        timestamp
    }
}
