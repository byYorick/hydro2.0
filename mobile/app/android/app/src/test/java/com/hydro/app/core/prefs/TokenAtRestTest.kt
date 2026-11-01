package com.hydro.app.core.prefs

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TokenAtRestTest {
	private val cipher = PrefixCipher()

	@Test
	fun plaintextLegacyValueNeedsMigrationAndStillDecodes() {
		assertTrue(TokenAtRest.needsMigration("legacy-token", cipher))
		assertEquals("legacy-token", TokenAtRest.decode("legacy-token", cipher))
	}

	@Test
	fun encodeThenDecodeRoundTrip() {
		val stored = TokenAtRest.encode("fresh-token", cipher)
		assertEquals("enc1:fresh-token", stored)
		assertFalse(TokenAtRest.needsMigration(stored, cipher))
		assertEquals("fresh-token", TokenAtRest.decode(stored, cipher))
	}

	@Test
	fun nullTokenClearsStorage() {
		assertNull(TokenAtRest.encode(null, cipher))
		assertNull(TokenAtRest.decode(null, cipher))
		assertFalse(TokenAtRest.needsMigration(null, cipher))
	}

	@Test
	fun corruptCiphertextDecodesToNull() {
		assertNull(TokenAtRest.decode("enc1:", cipher))
	}

	private class PrefixCipher : TokenCipher {
		override fun encrypt(plaintext: String): String = "enc1:$plaintext"

		override fun decrypt(stored: String): String? {
			if (!isEncrypted(stored)) {
				return null
			}
			val plain = stored.removePrefix("enc1:")
			return plain.ifEmpty { null }
		}

		override fun isEncrypted(stored: String): Boolean = stored.startsWith("enc1:")
	}
}
