package com.hydro.app.core.prefs

/**
 * Шифрование значения auth-токена перед записью в DataStore.
 * Контракт совпадает с SEC-03 (ветка cursor/sec-03-04-cleartext-secrets-01b1).
 */
interface TokenCipher {
	fun encrypt(plaintext: String): String

	/** null, если ciphertext повреждён или ключ недоступен. */
	fun decrypt(stored: String): String?

	fun isEncrypted(stored: String): Boolean
}
