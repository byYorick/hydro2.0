package com.hydro.app.features.auth.data

import com.hydro.app.core.prefs.PreferencesDataSource
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepository @Inject constructor(
	private val api: AuthApi,
	private val prefs: PreferencesDataSource
) {
	suspend fun login(email: String, password: String): Result<com.hydro.app.core.domain.User> {
		return try {
			val resp = api.login(LoginRequest(email, password))
			if (resp.status == "ok" && resp.data != null) {
				val token = resp.data.token
				if (token.isNotBlank()) {
					prefs.setToken(token)
				Result.success(resp.data.user)
				} else {
					Result.failure(Exception("Token is empty"))
				}
			} else {
				Result.failure(Exception(resp.message ?: "Login failed"))
			}
		} catch (t: Throwable) {
			Result.failure(t)
		}
	}

	suspend fun logout() {
		prefs.setToken(null)
	}
}


