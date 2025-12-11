package com.hydro.app.features.auth.data

import com.hydro.app.core.domain.LoginResponseData
import com.hydro.app.core.network.ApiResponse
import retrofit2.http.Body
import retrofit2.http.POST

data class LoginRequest(val email: String, val password: String)

interface AuthApi {
    @POST("/api/auth/login")
    suspend fun login(@Body body: LoginRequest): ApiResponse<LoginResponseData>
}
