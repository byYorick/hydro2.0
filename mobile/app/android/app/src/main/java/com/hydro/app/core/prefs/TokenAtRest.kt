package com.hydro.app.core.prefs

/**
 * Правила хранения токена: новое значение всегда шифруется,
 * уже записанный plaintext (старый DataStore) читается и помечается к миграции.
 */
internal object TokenAtRest {
	fun needsMigration(raw: String?, cipher: TokenCipher): Boolean {
		return !raw.isNullOrEmpty() && !cipher.isEncrypted(raw)
	}

	fun decode(raw: String?, cipher: TokenCipher): String? {
		if (raw.isNullOrEmpty()) {
			return null
		}
		if (!cipher.isEncrypted(raw)) {
			return raw
		}
		return cipher.decrypt(raw)
	}

	fun encode(token: String?, cipher: TokenCipher): String? {
		if (token == null) {
			return null
		}
		return cipher.encrypt(token)
	}
}
