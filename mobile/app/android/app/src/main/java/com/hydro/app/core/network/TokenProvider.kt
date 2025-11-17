package com.hydro.app.core.network

import com.hydro.app.core.prefs.PreferencesDataSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn

class TokenProvider(preferences: PreferencesDataSource) {
	private val scope = CoroutineScope(Dispatchers.IO)
	val tokenState: StateFlow<String?> =
		preferences.tokenFlow.stateIn(scope, SharingStarted.Eagerly, null)
}


