package com.hydro.app.core.prefs

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = PreferencesKeys.DATASTORE_NAME)

class PreferencesDataSource(private val appContext: Context) {
    private val tokenKey = stringPreferencesKey(PreferencesKeys.KEY_TOKEN)
    private val baseUrlKey = stringPreferencesKey(PreferencesKeys.KEY_BASE_URL)
    private val wsUrlKey = stringPreferencesKey(PreferencesKeys.KEY_WS_URL)

	val tokenFlow: Flow<String?> = appContext.dataStore.data.map { it[tokenKey] }
	val baseUrlFlow: Flow<String?> = appContext.dataStore.data.map { it[baseUrlKey] }
	val wsUrlFlow: Flow<String?> = appContext.dataStore.data.map { it[wsUrlKey] }

	suspend fun setToken(token: String?) {
		appContext.dataStore.edit { prefs ->
			if (token == null) prefs.remove(tokenKey) else prefs[tokenKey] = token
		}
	}

	suspend fun setBaseUrl(url: String?) {
		appContext.dataStore.edit { prefs ->
			if (url == null) prefs.remove(baseUrlKey) else prefs[baseUrlKey] = url
		}
	}

	suspend fun setWsUrl(url: String?) {
		appContext.dataStore.edit { prefs ->
			if (url == null) prefs.remove(wsUrlKey) else prefs[wsUrlKey] = url
		}
	}
}


