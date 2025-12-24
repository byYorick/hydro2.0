package com.hydro.app.core.config

import android.content.Context
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.hydro.app.BuildConfig
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.InputStream
import javax.inject.Inject
import javax.inject.Singleton

data class EnvConfig(
    val apiBaseUrl: String,
    val env: String
)

/**
 * Загрузчик конфигурации приложения из assets.
 * 
 * Загружает конфигурационный файл в зависимости от build flavor:
 * - dev: env.dev.json
 * - staging: env.staging.json
 * - prod: env.prod.json
 * 
 * Конфигурация кэшируется после первой загрузки.
 */
@Singleton
class ConfigLoader @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val gson = Gson()
    private var cachedConfig: EnvConfig? = null

    /**
     * Загружает конфигурацию приложения.
     * 
     * При первой загрузке читает файл из assets и кэширует результат.
     * При последующих вызовах возвращает закэшированную конфигурацию.
     * 
     * @return Конфигурация приложения
     * @throws IllegalStateException если конфигурационный файл не найден или некорректен
     */
    fun loadConfig(): EnvConfig {
        cachedConfig?.let { return it }
        
        return try {
            val configFileName = BuildConfig.ENV_CONFIG_FILE
            android.util.Log.d("ConfigLoader", "Loading config from: configs/$configFileName")
            val inputStream: InputStream = context.assets.open("configs/$configFileName")
            val jsonString = inputStream.bufferedReader().use { it.readText() }
            val jsonObject = gson.fromJson(jsonString, JsonObject::class.java)
            
            val apiBaseUrl = jsonObject.get("API_BASE_URL")?.asString 
                ?: throw IllegalStateException("API_BASE_URL not found in config")
            val env = jsonObject.get("ENV")?.asString 
                ?: throw IllegalStateException("ENV not found in config")
            
            android.util.Log.d("ConfigLoader", "Loaded config: API_BASE_URL=$apiBaseUrl, ENV=$env")
            
            val config = EnvConfig(
                apiBaseUrl = apiBaseUrl,
                env = env
            )
            cachedConfig = config
            config
        } catch (e: Exception) {
            // Fallback to default if config file not found
            // Используем 10.0.2.2 для эмулятора Android (localhost хост-машины)
            android.util.Log.e("ConfigLoader", "Failed to load config: ${e.message}", e)
            val fallbackUrl = "http://10.0.2.2:8080"
            android.util.Log.w("ConfigLoader", "Using fallback config: API_BASE_URL=$fallbackUrl")
            EnvConfig(
                apiBaseUrl = fallbackUrl,
                env = "DEV"
            )
        }
    }
}

