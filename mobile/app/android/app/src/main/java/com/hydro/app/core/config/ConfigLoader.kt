package com.hydro.app.core.config

import android.content.Context
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.hydro.app.BuildConfig
import java.io.InputStream
import javax.inject.Inject
import javax.inject.Singleton

data class EnvConfig(
    val apiBaseUrl: String,
    val env: String
)

@Singleton
class ConfigLoader @Inject constructor(
    private val context: Context
) {
    private val gson = Gson()
    private var cachedConfig: EnvConfig? = null

    fun loadConfig(): EnvConfig {
        cachedConfig?.let { return it }
        
        return try {
            val configFileName = BuildConfig.ENV_CONFIG_FILE
            val inputStream: InputStream = context.assets.open("configs/$configFileName")
            val jsonString = inputStream.bufferedReader().use { it.readText() }
            val jsonObject = gson.fromJson(jsonString, JsonObject::class.java)
            
            val config = EnvConfig(
                apiBaseUrl = jsonObject.get("API_BASE_URL")?.asString 
                    ?: throw IllegalStateException("API_BASE_URL not found in config"),
                env = jsonObject.get("ENV")?.asString 
                    ?: throw IllegalStateException("ENV not found in config")
            )
            cachedConfig = config
            config
        } catch (e: Exception) {
            // Fallback to default if config file not found
            android.util.Log.e("ConfigLoader", "Failed to load config: ${e.message}", e)
            EnvConfig(
                apiBaseUrl = "http://localhost:8080",
                env = "DEV"
            )
        }
    }
}

