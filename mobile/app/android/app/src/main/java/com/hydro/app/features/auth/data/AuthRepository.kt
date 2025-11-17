package com.hydro.app.features.auth.data

import com.hydro.app.core.prefs.PreferencesDataSource
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepository @Inject constructor(
	private val api: AuthApi,
	private val prefs: PreferencesDataSource
) {
	suspend fun login(email: String, password: String): Result<Unit> {
		return try {
			val resp = api.login(LoginRequest(email, password))
			prefs.setToken(resp.token)
			Result.success(Unit)
		} catch (t: Throwable) {
			Result.failure(t)
		}
	}

	suspend fun logout() {
		prefs.setToken(null)
	}
}


