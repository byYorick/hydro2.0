package com.hydro.app.core.network

import com.hydro.app.core.i18n.ErrorCatalog
import com.hydro.app.core.i18n.HumanErrorInput
import com.squareup.moshi.Moshi
import com.squareup.moshi.adapter
import retrofit2.HttpException
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ApiErrorParser @Inject constructor(
    private val moshi: Moshi,
    private val errorCatalog: ErrorCatalog,
) {
    private val adapter = moshi.adapter<ApiErrorBody>()

    fun fromApiResponse(
        status: String?,
        message: String?,
        code: String?,
        humanErrorMessage: String? = null,
    ): String {
        if (status == "ok") {
            return message?.trim().orEmpty()
        }
        return errorCatalog.resolve(
            HumanErrorInput(
                code = code,
                message = message,
                humanMessage = humanErrorMessage,
            ),
        )
    }

    fun parseHttpException(exception: HttpException): String {
        val body = exception.response()?.errorBody()?.string()
        return parseJson(body) ?: errorCatalog.resolveHttpStatus(exception.code())
    }

    fun parseJson(body: String?): String {
        if (body.isNullOrBlank()) {
            return ErrorCatalog.GENERIC_MESSAGE
        }
        return try {
            val payload = adapter.fromJson(body)
            if (payload != null) {
                errorCatalog.resolve(
                    HumanErrorInput(
                        code = payload.code,
                        message = payload.message,
                        humanMessage = payload.humanErrorMessage,
                    ),
                )
            } else {
                ErrorCatalog.GENERIC_MESSAGE
            }
        } catch (_: Exception) {
            ErrorCatalog.GENERIC_MESSAGE
        }
    }

    fun localizedMessage(throwable: Throwable): String {
        return when (throwable) {
            is HttpException -> parseHttpException(throwable)
            else -> {
                val raw = throwable.message?.trim().orEmpty()
                if (raw.isEmpty()) {
                    ErrorCatalog.GENERIC_MESSAGE
                } else {
                    errorCatalog.resolve(HumanErrorInput(message = raw), fallback = raw)
                }
            }
        }
    }
}
