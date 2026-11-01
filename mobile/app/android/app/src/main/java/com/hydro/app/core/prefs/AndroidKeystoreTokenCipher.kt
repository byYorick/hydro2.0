package com.hydro.app.core.prefs

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * AES-256-GCM через Android Keystore. В DataStore пишется только ciphertext
 * с префиксом [PREFIX], ключ из приложения не экспортируется.
 */
class AndroidKeystoreTokenCipher : TokenCipher {
	override fun encrypt(plaintext: String): String {
		val cipher = Cipher.getInstance(TRANSFORMATION)
		cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
		val iv = cipher.iv
		val ciphertext = cipher.doFinal(plaintext.toByteArray(Charsets.UTF_8))
		val payload = ByteArray(iv.size + ciphertext.size)
		System.arraycopy(iv, 0, payload, 0, iv.size)
		System.arraycopy(ciphertext, 0, payload, iv.size, ciphertext.size)
		return PREFIX + Base64.encodeToString(payload, Base64.NO_WRAP)
	}

	override fun decrypt(stored: String): String? {
		if (!isEncrypted(stored)) {
			return null
		}
		return try {
			val payload = Base64.decode(stored.removePrefix(PREFIX), Base64.NO_WRAP)
			if (payload.size <= IV_SIZE_BYTES) {
				return null
			}
			val iv = payload.copyOfRange(0, IV_SIZE_BYTES)
			val ciphertext = payload.copyOfRange(IV_SIZE_BYTES, payload.size)
			val cipher = Cipher.getInstance(TRANSFORMATION)
			cipher.init(
				Cipher.DECRYPT_MODE,
				getOrCreateKey(),
				GCMParameterSpec(TAG_BITS, iv),
			)
			cipher.doFinal(ciphertext).toString(Charsets.UTF_8)
		} catch (_: Exception) {
			null
		}
	}

	override fun isEncrypted(stored: String): Boolean = stored.startsWith(PREFIX)

	private fun getOrCreateKey(): SecretKey {
		val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
		val existing = keyStore.getKey(KEY_ALIAS, null) as? SecretKey
		if (existing != null) {
			return existing
		}
		val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
		val spec = KeyGenParameterSpec.Builder(
			KEY_ALIAS,
			KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
		)
			.setBlockModes(KeyProperties.BLOCK_MODE_GCM)
			.setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
			.setKeySize(256)
			.setRandomizedEncryptionRequired(true)
			.build()
		generator.init(spec)
		return generator.generateKey()
	}

	private companion object {
		const val PREFIX = "enc1:"
		const val ANDROID_KEYSTORE = "AndroidKeyStore"
		const val KEY_ALIAS = "hydro_auth_token_aes"
		const val TRANSFORMATION = "AES/GCM/NoPadding"
		const val IV_SIZE_BYTES = 12
		const val TAG_BITS = 128
	}
}
