package com.hydro.app.features.auth.data

import retrofit2.http.Body
import retrofit2.http.POST

data class LoginRequest(val email: String, val password: String)
data class LoginResponse(val token: String)

interface AuthApi {
	@POST("/api/auth/login")
	suspend fun login(@Body body: LoginRequest): LoginResponse
}


