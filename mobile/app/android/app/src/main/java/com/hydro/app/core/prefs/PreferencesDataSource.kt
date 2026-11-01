package com.hydro.app.core.prefs

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emitAll
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

private val Context.dataStore by preferencesDataStore(name = PreferencesKeys.DATASTORE_NAME)

/**
 * Настройки приложения.
 *
 * Auth-токен хранится в DataStore только в зашифрованном виде
 * ([AndroidKeystoreTokenCipher]). Plaintext из прежних версий читается
 * и перезаписывается ciphertext при первом обращении.
 */
class PreferencesDataSource(
	private val store: DataStore<Preferences>,
	private val tokenCipher: TokenCipher,
) {
	constructor(appContext: Context, tokenCipher: TokenCipher = AndroidKeystoreTokenCipher()) : this(
		appContext.dataStore,
		tokenCipher,
	)

	private val tokenKey = stringPreferencesKey(PreferencesKeys.KEY_TOKEN)
	private val baseUrlKey = stringPreferencesKey(PreferencesKeys.KEY_BASE_URL)
	private val wsUrlKey = stringPreferencesKey(PreferencesKeys.KEY_WS_URL)
	private val loginTimeKey = longPreferencesKey(PreferencesKeys.KEY_LOGIN_TIME)
	private val lastActivityTimeKey = longPreferencesKey(PreferencesKeys.KEY_LAST_ACTIVITY_TIME)
	private val tokenMutex = Mutex()

	val tokenFlow: Flow<String?> = flow {
		migrateLegacyToken()
		emitAll(
			store.data.map { prefs ->
				TokenAtRest.decode(prefs[tokenKey], tokenCipher)
			},
		)
	}
	val baseUrlFlow: Flow<String?> = store.data.map { it[baseUrlKey] }
	val wsUrlFlow: Flow<String?> = store.data.map { it[wsUrlKey] }
	val loginTimeFlow: Flow<Long?> = store.data.map { it[loginTimeKey] }
	val lastActivityTimeFlow: Flow<Long?> = store.data.map { it[lastActivityTimeKey] }

	suspend fun setToken(token: String?) {
		tokenMutex.withLock {
			store.edit { prefs ->
				if (token == null) {
					prefs.remove(tokenKey)
					prefs.remove(loginTimeKey)
					prefs.remove(lastActivityTimeKey)
				} else {
					prefs[tokenKey] = TokenAtRest.encode(token, tokenCipher)
						?: error("Token cipher returned empty ciphertext")
					val currentTime = System.currentTimeMillis()
					prefs[loginTimeKey] = currentTime
					prefs[lastActivityTimeKey] = currentTime
				}
			}
		}
	}

	/**
	 * Обновляет время последней активности пользователя.
	 */
	suspend fun updateLastActivityTime() {
		store.edit { prefs ->
			prefs[lastActivityTimeKey] = System.currentTimeMillis()
		}
	}

	suspend fun getLoginTime(): Long? {
		return store.data.first()[loginTimeKey]
	}

	suspend fun getLastActivityTime(): Long? {
		return store.data.first()[lastActivityTimeKey]
	}

	suspend fun setBaseUrl(url: String?) {
		store.edit { prefs ->
			if (url == null) prefs.remove(baseUrlKey) else prefs[baseUrlKey] = url
		}
	}

	suspend fun setWsUrl(url: String?) {
		store.edit { prefs ->
			if (url == null) prefs.remove(wsUrlKey) else prefs[wsUrlKey] = url
		}
	}

	private suspend fun migrateLegacyToken() {
		tokenMutex.withLock {
			val raw = store.data.first()[tokenKey]
			if (!TokenAtRest.needsMigration(raw, tokenCipher)) {
				return
			}
			val encrypted = TokenAtRest.encode(raw, tokenCipher) ?: return
			store.edit { prefs ->
				prefs[tokenKey] = encrypted
			}
		}
	}
}
