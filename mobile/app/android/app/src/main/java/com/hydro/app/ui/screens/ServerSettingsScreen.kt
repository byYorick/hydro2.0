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
            Text("Адрес Laravel в локальной сети. Для эмулятора оставьте 10.0.2.2 и порт 8080. Для телефона укажите LAN IP компьютера, где запущен make up.")
            OutlinedTextField(
                value = state.host,
                onValueChange = vm::onHost,
                label = { Text("IP или хост") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = state.port,
                onValueChange = vm::onPort,
                label = { Text("Порт") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth(),
            )
            Column {
                Text("HTTPS")
                Switch(checked = state.useHttps, onCheckedChange = vm::onHttps)
                Text(
                    if (state.cleartextAllowed) {
                        "Debug-сборка: HTTP для локальной сети разрешён."
                    } else {
                        "Release: нужен HTTPS. HTTP только с флагом сборки hydro.allowCleartext=true."
                    },
                )
            }
            Text(
                "Токен Sanctum пишется в DataStore только как AES-256-GCM (Android Keystore), как в SEC-03. Открытый токен с прошлых версий перешифровывается при чтении.",
            )
            state.message?.let { Text(it) }
            Spacer(Modifier.height(8.dp))
            Button(onClick = vm::save, modifier = Modifier.fillMaxWidth()) {
                Text("Сохранить")
            }
        }
    }
}
