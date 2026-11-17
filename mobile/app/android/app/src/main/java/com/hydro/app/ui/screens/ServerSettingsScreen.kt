package com.hydro.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hydro.app.features.settings.ServerSettingsViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ServerSettingsScreen(
    onBack: () -> Unit,
    vm: ServerSettingsViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Сервер") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Укажите адрес сервера Hydro, доступный с этого устройства. Имя сервера, порт и HTTPS задаются отдельно. Изменения применяются кнопкой «Сохранить». Сохранение адреса не проверяет доступность сервера.")
            OutlinedTextField(
                value = state.host,
                onValueChange = vm::onHost,
                label = { Text("Имя сервера или IPv4-адрес") },
                supportingText = { Text(state.hostError ?: "Например: hydro.local или 192.168.1.20") },
                isError = state.hostError != null,
                enabled = !state.saving,
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = state.port,
                onValueChange = vm::onPort,
                label = { Text("Порт") },
                supportingText = { Text(state.portError ?: "Номер порта сервера, например 8080 или 443") },
                isError = state.portError != null,
                enabled = !state.saving,
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth(),
            )
            Column {
                Text("HTTPS")
                Switch(checked = state.useHttps, onCheckedChange = vm::onHttps, enabled = state.cleartextAllowed && !state.saving)
                Text(
                    if (state.cleartextAllowed) {
                        "В этой сборке разрешено подключение по HTTP."
                    } else {
                        "В этой сборке требуется защищённое подключение HTTPS."
                    },
                )
            }
            Text(
                "Данные входа сохраняются в защищённом хранилище устройства. Изменение адреса сервера не меняет настройки полива.",
            )
            state.message?.let { Text(it) }
            Spacer(Modifier.height(8.dp))
            Button(onClick = vm::save, enabled = !state.saving && !state.saved && state.hostError == null && state.portError == null, modifier = Modifier.fillMaxWidth()) {
                Text(if (state.saving) "Сохранение…" else if (state.saved) "Сохранено" else "Сохранить")
            }
        }
    }
}
