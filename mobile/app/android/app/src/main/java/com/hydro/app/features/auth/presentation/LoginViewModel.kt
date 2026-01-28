package com.hydro.app.features.auth.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hydro.app.core.auth.SessionManager
import com.hydro.app.core.domain.AppError
import com.hydro.app.core.domain.User
import com.hydro.app.core.domain.usecase.LoginUseCase
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Состояние экрана входа.
 */
sealed interface LoginState {
	/** Начальное состояние. */
	data object Idle : LoginState
	
	/** Идет процесс авторизации. */
	data object Loading : LoginState
	
	/** Успешная авторизация. */
	data class Success(val user: User) : LoginState
	
	/** Ошибка авторизации. */
	data class Error(val message: String) : LoginState
}

/**
 * ViewModel для экрана входа.
 * 
 * Использует LoginUseCase для выполнения авторизации с валидацией данных.
 */
@HiltViewModel
class LoginViewModel @Inject constructor(
	private val loginUseCase: LoginUseCase,
	private val sessionManager: SessionManager
) : ViewModel() {
	private val _state = MutableStateFlow<LoginState>(LoginState.Idle)
	
	/**
	 * Текущее состояние экрана входа.
	 */
	val state: StateFlow<LoginState> = _state

	/**
	 * Выполняет вход пользователя.
	 * 
	 * @param email Email пользователя
	 * @param password Пароль пользователя
	 */
	fun login(email: String, password: String) {
		_state.value = LoginState.Loading
		viewModelScope.launch {
			val result = loginUseCase.invoke(email, password)
			_state.value = result.fold(
				onSuccess = { user -> 
					// Обновляем время активности после успешного входа
					sessionManager.updateActivity()
					LoginState.Success(user) 
				},
				onFailure = { error ->
					LoginState.Error(
						when (error) {
							is AppError.ValidationError -> error.message
							is AppError.AuthError -> error.message
							is AppError.NetworkError -> "Network error. Please check your connection."
							else -> error.message ?: "An error occurred"
						}
					)
				}
			)
		}
	}
}


