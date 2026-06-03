package com.hydro.app.features.auth.data

import android.util.Log
import com.hydro.app.core.network.ApiErrorParser
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
	private val prefs: PreferencesDataSource,
	private val apiErrorParser: ApiErrorParser,
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
				val localized = apiErrorParser.fromApiResponse(
					status = resp.status,
					message = resp.message,
					code = resp.code,
					humanErrorMessage = resp.humanErrorMessage,
				)
				Log.e("AuthRepository", "Login failed: $localized")
				Result.failure(Exception(localized))
			}
		} catch (e: HttpException) {
			val errorBody = e.response()?.errorBody()?.string() ?: "No error body"
			Log.e("AuthRepository", "HTTP error ${e.code()}: $errorBody", e)
			Result.failure(Exception(apiErrorParser.parseHttpException(e)))
		} catch (e: ConnectException) {
			Log.e("AuthRepository", "Connection error: ${e.message}", e)
			Result.failure(Exception("Не удалось подключиться к серверу. Проверьте сеть и доступность backend."))
		} catch (e: SocketTimeoutException) {
			Log.e("AuthRepository", "Timeout error: ${e.message}", e)
			Result.failure(Exception("Превышено время ожидания ответа сервера."))
		} catch (e: UnknownHostException) {
			Log.e("AuthRepository", "Unknown host error: ${e.message}", e)
			Result.failure(Exception("Не удалось определить адрес сервера. Проверьте настройки сети."))
		} catch (e: IOException) {
			Log.e("AuthRepository", "IO error: ${e.message}", e)
			Result.failure(Exception("Ошибка сети. Проверьте подключение."))
		} catch (t: Throwable) {
			Log.e("AuthRepository", "Unexpected error: ${t.message}", t)
			Result.failure(Exception(apiErrorParser.localizedMessage(t)))
		}
	}

	suspend fun logout() {
		prefs.setToken(null)
		// Время входа и активности будет очищено автоматически в setToken
	}
}


