package com.hydro.app.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hydro.app.features.provisioning.ProvisioningViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProvisioningScreen(
    onBack: () -> Unit,
    vm: ProvisioningViewModel = hiltViewModel(),
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
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            when (val current = state.value) {
                is ProvisioningViewModel.ProvisioningState.Idle -> {
                    Button(onClick = { vm.scanDevices() }, modifier = Modifier.fillMaxWidth()) {
                        Text("Сканировать устройства")
                    }
                }
                is ProvisioningViewModel.ProvisioningState.Scanning -> {
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.CenterHorizontally))
                    Text("Поиск устройств...", modifier = Modifier.align(Alignment.CenterHorizontally))
                }
                is ProvisioningViewModel.ProvisioningState.FoundDevices -> {
                    Text("Найденные устройства:", fontSize = 18.sp, fontWeight = FontWeight.Bold)
                    current.devices.forEach { device ->
                        Card(modifier = Modifier.fillMaxWidth().clickable { }) {
                            Text(device.ssid, modifier = Modifier.padding(16.dp))
                        }
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    OutlinedTextField(value = wifiSsid, onValueChange = { wifiSsid = it }, label = { Text("SSID Wi-Fi сети") }, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(value = wifiPassword, onValueChange = { wifiPassword = it }, label = { Text("Пароль Wi-Fi") }, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(value = nodeName, onValueChange = { nodeName = it }, label = { Text("Имя узла") }, modifier = Modifier.fillMaxWidth())
                    if (current.devices.isNotEmpty()) {
                        Button(
                            onClick = {
                                vm.provisionDevice(
                                    current.devices.first(),
                                    ProvisioningViewModel.ProvisioningConfig(
                                        wifiSsid = wifiSsid,
                                        wifiPassword = wifiPassword,
                                        nodeName = nodeName,
                                    ),
                                )
                            },
                            modifier = Modifier.fillMaxWidth(),
                            enabled = wifiSsid.isNotBlank() && wifiPassword.isNotBlank() && nodeName.isNotBlank(),
                        ) { Text("Настроить узел") }
                    }
                }
                is ProvisioningViewModel.ProvisioningState.Configuring -> {
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.CenterHorizontally))
                    Text("Настройка узла...", modifier = Modifier.align(Alignment.CenterHorizontally))
                }
                is ProvisioningViewModel.ProvisioningState.Success -> {
                    Text("Узел успешно настроен!", color = MaterialTheme.colorScheme.primary, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                }
                is ProvisioningViewModel.ProvisioningState.Error -> {
                    Text("Ошибка: ${current.message}", color = MaterialTheme.colorScheme.error)
                    Button(onClick = { vm.scanDevices() }, modifier = Modifier.fillMaxWidth()) { Text("Повторить") }
                }
            }
        }
    }
}
