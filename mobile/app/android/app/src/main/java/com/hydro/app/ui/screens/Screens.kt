package com.hydro.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Button
import androidx.compose.material3.Divider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import com.hydro.app.features.auth.presentation.LoginState
import com.hydro.app.features.auth.presentation.LoginViewModel
import com.hydro.app.features.alerts.AlertsViewModel
import com.hydro.app.features.greenhouses.GreenhousesViewModel
import com.hydro.app.features.zones.ZoneDetailsViewModel
import com.hydro.app.features.zones.ZonesViewModel

@Composable
fun LoginScreen(onLoggedIn: () -> Unit, vm: LoginViewModel = hiltViewModel()) {
	val state = vm.state.collectAsState()
	LaunchedEffect(state.value) {
		if (state.value is LoginState.Success) onLoggedIn()
	}
	Column(
		modifier = Modifier.fillMaxSize(),
		horizontalAlignment = Alignment.CenterHorizontally,
		verticalArrangement = Arrangement.Center
	) {
		Text(text = "Hydro 2.0 — Login")
		when (val s = state.value) {
			is LoginState.Idle -> Button(onClick = { vm.login("demo@hydro.local", "demo") }) { Text("Войти (demo)") }
			is LoginState.Loading -> CircularProgressIndicator()
			is LoginState.Error -> {
				Text("Ошибка: ${s.message}")
				Button(onClick = { vm.login("demo@hydro.local", "demo") }) { Text("Повторить") }
			}
			is LoginState.Success -> {}
		}
	}
}

@Composable
fun GreenhousesScreen(
	onOpenZones: () -> Unit,
	onOpenAlerts: () -> Unit,
	onProvisioning: () -> Unit
) {
	val vm: GreenhousesViewModel = hiltViewModel()
	val state = vm.state.collectAsState()
	LaunchedEffect(Unit) { vm.load() }
	Column(
		modifier = Modifier.fillMaxSize(),
		horizontalAlignment = Alignment.CenterHorizontally,
		verticalArrangement = Arrangement.Center
	) {
		Text(text = "Теплицы")
		if (state.value.isEmpty()) {
			CircularProgressIndicator()
		} else {
			state.value.forEach { gh ->
				Text("- ${gh.name} (${gh.id})")
			}
			Divider()
		}
		Button(onClick = onOpenZones) { Text("Перейти к зонам") }
		Button(onClick = onOpenAlerts) { Text("Алерты") }
		Button(onClick = onProvisioning) { Text("Provisioning узла") }
	}
}

@Composable
fun ZonesScreen(onOpenZone: (String) -> Unit) {
	val vm: ZonesViewModel = hiltViewModel()
	val state = vm.state.collectAsState()
	LaunchedEffect(Unit) { vm.load("gh-main") }
	Column(
		modifier = Modifier.fillMaxSize(),
		horizontalAlignment = Alignment.CenterHorizontally,
		verticalArrangement = Arrangement.Center
	) {
		Text(text = "Список зон")
		if (state.value.isEmpty()) {
			CircularProgressIndicator()
		} else {
			state.value.forEach { zone ->
				Button(onClick = { onOpenZone(zone.id) }) { Text("Открыть зону ${zone.name}") }
			}
		}
	}
}

@Composable
fun ZoneDetailsScreen(onBack: () -> Unit) {
	val vm: ZoneDetailsViewModel = hiltViewModel()
	val state = vm.state.collectAsState()
	LaunchedEffect(Unit) { vm.load("zone-1") }
	Column(
		modifier = Modifier.fillMaxSize(),
		horizontalAlignment = Alignment.CenterHorizontally,
		verticalArrangement = Arrangement.Center
	) {
		Text(text = "Детали зоны")
		when (val t = state.value) {
			null -> CircularProgressIndicator()
			else -> {
				Text("pH: ${t.ph ?: "-"}")
				Text("EC: ${t.ec ?: "-"}")
				Text("T: ${t.airTemp ?: "-"}  H: ${t.airHumidity ?: "-"}")
			}
		}
		Button(onClick = onBack) { Text("Назад") }
	}
}

@Composable
fun AlertsScreen(onBack: () -> Unit) {
	val vm: AlertsViewModel = hiltViewModel()
	val state = vm.state.collectAsState()
	LaunchedEffect(Unit) { vm.load() }
	Column(
		modifier = Modifier.fillMaxSize(),
		horizontalAlignment = Alignment.CenterHorizontally,
		verticalArrangement = Arrangement.Center
	) {
		Text(text = "Алерты")
		if (state.value.isEmpty()) {
			Text("Пока пусто")
		} else {
			state.value.forEach { a ->
				Text("${a.level} ${a.type} @ ${a.zoneId} — ${a.message}")
			}
		}
		Button(onClick = onBack) { Text("Назад") }
	}
}

@Composable
fun ProvisioningScreen(onBack: () -> Unit) {
	val vm: com.hydro.app.features.provisioning.ProvisioningViewModel = hiltViewModel()
	val state = vm.state.collectAsState()
	Column(
		modifier = Modifier.fillMaxSize(),
		horizontalAlignment = Alignment.CenterHorizontally,
		verticalArrangement = Arrangement.Center
	) {
		Text(text = "Provisioning узла (заглушка)")
		if (state.value != null) Text("Результат: ${'$'}{state.value}")
		Button(onClick = { vm.sendDemo() }) { Text("Отправить конфиг (demo)") }
		Button(onClick = onBack) { Text("Назад") }
	}
}


