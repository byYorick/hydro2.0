package com.hydro.app.core.prefs

/**
 * Шифрование значения auth-токена перед записью в DataStore.
 */
interface TokenCipher {
	fun encrypt(plaintext: String): String

	/** null, если ciphertext повреждён или ключ недоступен. */
	fun decrypt(stored: String): String?

	fun isEncrypted(stored: String): Boolean
}
