package com.hydro.app.features.auth.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hydro.app.features.auth.data.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed interface LoginState {
	data object Idle : LoginState
	data object Loading : LoginState
	data object Success : LoginState
	data class Error(val message: String) : LoginState
}

@HiltViewModel
class LoginViewModel @Inject constructor(
	private val authRepository: AuthRepository
) : ViewModel() {
	private val _state = MutableStateFlow<LoginState>(LoginState.Idle)
	val state: StateFlow<LoginState> = _state

	fun login(email: String, password: String) {
		_state.value = LoginState.Loading
		viewModelScope.launch {
			val res = authRepository.login(email, password)
			_state.value = res.fold(
				onSuccess = { LoginState.Success },
				onFailure = { LoginState.Error(it.message ?: "Login failed") }
			)
		}
	}
}


