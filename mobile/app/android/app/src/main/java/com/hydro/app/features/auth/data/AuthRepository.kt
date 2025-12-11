package com.hydro.app.features.auth.data

import android.util.Log
import com.hydro.app.core.prefs.PreferencesDataSource
import retrofit2.HttpException
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepository @Inject constructor(
	private val api: AuthApi,
	private val prefs: PreferencesDataSource
) {
	suspend fun login(email: String, password: String): Result<com.hydro.app.core.domain.User> {
		return try {
			Log.d("AuthRepository", "Attempting login for: $email")
			val resp = api.login(LoginRequest(email, password))
			if (resp.status == "ok" && resp.data != null) {
				val token = resp.data.token
				if (token.isNotBlank()) {
					prefs.setToken(token)
					Log.d("AuthRepository", "Login successful for: $email")
					return Result.success(resp.data.user)
				} else {
					Log.e("AuthRepository", "Token is empty in response")
					return Result.failure(Exception("Token is empty"))
				}
			} else {
				Log.e("AuthRepository", "Login failed: ${resp.message}")
				Result.failure(Exception(resp.message ?: "Login failed"))
			}
		} catch (e: HttpException) {
			val errorBody = e.response()?.errorBody()?.string() ?: "No error body"
			Log.e("AuthRepository", "HTTP error ${e.code()}: $errorBody", e)
			when (e.code()) {
				401 -> Result.failure(Exception("Invalid email or password"))
				403 -> Result.failure(Exception("Access forbidden"))
				404 -> Result.failure(Exception("Server endpoint not found"))
				500 -> Result.failure(Exception("Server error"))
				else -> Result.failure(Exception("HTTP error ${e.code()}: ${e.message()}"))
			}
		} catch (e: ConnectException) {
			Log.e("AuthRepository", "Connection error: ${e.message}", e)
			Result.failure(Exception("Cannot connect to server. Check your network connection and ensure the backend is running."))
		} catch (e: SocketTimeoutException) {
			Log.e("AuthRepository", "Timeout error: ${e.message}", e)
			Result.failure(Exception("Connection timeout. The server is taking too long to respond."))
		} catch (e: UnknownHostException) {
			Log.e("AuthRepository", "Unknown host error: ${e.message}", e)
			Result.failure(Exception("Cannot resolve server address. Check your network configuration."))
		} catch (e: IOException) {
			Log.e("AuthRepository", "IO error: ${e.message}", e)
			Result.failure(Exception("Network error: ${e.message}"))
		} catch (t: Throwable) {
			Log.e("AuthRepository", "Unexpected error: ${t.message}", t)
			Result.failure(Exception("Unexpected error: ${t.message}"))
		}
	}

	suspend fun logout() {
		prefs.setToken(null)
		// Время входа и активности будет очищено автоматически в setToken
	}
}


