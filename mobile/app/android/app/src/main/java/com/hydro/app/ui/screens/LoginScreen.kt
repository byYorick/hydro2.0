package com.hydro.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hydro.app.features.auth.presentation.LoginState
import com.hydro.app.features.auth.presentation.LoginViewModel

@Composable
fun LoginScreen(
    onLoggedIn: () -> Unit,
    onOpenSettings: () -> Unit = {},
    vm: LoginViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    val server by vm.serverLabel.collectAsState()
    LaunchedEffect(state) {
        if (state is LoginState.Success) onLoggedIn()
    }
    LoginScreenContent(
        serverLabel = server,
        state = state,
        onLogin = vm::login,
        onOpenSettings = onOpenSettings,
    )
}

@Composable
fun LoginScreenContent(
    serverLabel: String,
    state: LoginState,
    onLogin: (String, String) -> Unit,
    onOpenSettings: () -> Unit,
) {
    var email = androidx.compose.runtime.remember { androidx.compose.runtime.mutableStateOf("") }
    var password = androidx.compose.runtime.remember { androidx.compose.runtime.mutableStateOf("") }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("Hydro 2.0", fontSize = 36.sp, fontWeight = FontWeight.Bold)
        Text(
            "Оператор теплицы",
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = onOpenSettings) {
            Text("Сервер: $serverLabel")
        }
        Spacer(Modifier.height(16.dp))
        OutlinedTextField(
            value = email.value,
            onValueChange = { email.value = it },
            label = { Text("Email") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = password.value,
            onValueChange = { password.value = it },
            label = { Text("Пароль") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(20.dp))
        when (state) {
            LoginState.Loading -> CircularProgressIndicator()
            is LoginState.Error -> {
                Text(state.message, color = MaterialTheme.colorScheme.error)
                Spacer(Modifier.height(12.dp))
                Button(
                    onClick = { onLogin(email.value.trim(), password.value) },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Повторить") }
            }
            else -> Button(
                onClick = { onLogin(email.value.trim(), password.value) },
                enabled = email.value.isNotBlank() && password.value.isNotBlank(),
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Войти") }
        }
    }
}
