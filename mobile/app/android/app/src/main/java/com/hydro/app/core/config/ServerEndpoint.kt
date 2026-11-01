package com.hydro.app.core.config

/**
 * Адрес Laravel на локальной сети. По умолчанию — хост эмулятора Android.
 */
data class ServerEndpoint(
    val host: String,
    val port: Int,
    val useHttps: Boolean,
) {
    fun baseUrl(): String {
        val scheme = if (useHttps) "https" else "http"
        return "$scheme://$host:$port/"
    }

    fun label(): String = "${if (useHttps) "https" else "http"}://$host:$port"

    companion object {
        const val DEFAULT_HOST = "10.0.2.2"
        const val DEFAULT_PORT = 8080

        val emulatorDefault = ServerEndpoint(DEFAULT_HOST, DEFAULT_PORT, useHttps = false)

        fun parse(hostRaw: String, portRaw: String, useHttps: Boolean): Result<ServerEndpoint> {
            val host = hostRaw.trim()
                .removePrefix("https://")
                .removePrefix("http://")
                .trimEnd('/')
                .substringBefore('/')
                .substringBefore(':')
            if (host.isBlank() || host.any { it.isWhitespace() }) {
                return Result.failure(IllegalArgumentException("Укажите IP или имя хоста без пробелов"))
            }
            val port = portRaw.trim().toIntOrNull()
                ?: return Result.failure(IllegalArgumentException("Порт должен быть числом"))
            if (port !in 1..65535) {
                return Result.failure(IllegalArgumentException("Порт должен быть от 1 до 65535"))
            }
            return Result.success(ServerEndpoint(host, port, useHttps))
        }
    }
}

/**
 * Cleartext HTTP разрешён только в debug-сборке или при явном флаге `hydro.allowCleartext=true`.
 */
object CleartextPolicy {
    fun allows(endpoint: ServerEndpoint, debugBuild: Boolean, allowCleartextFlag: Boolean): Boolean {
        if (endpoint.useHttps) return true
        return debugBuild || allowCleartextFlag
    }

    fun rejectionMessage(): String =
        "HTTP без TLS запрещён в release. Укажите HTTPS или соберите debug (либо -Phydro.allowCleartext=true)."
}
