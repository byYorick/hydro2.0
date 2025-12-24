package com.hydro.app.features.auth.di

import com.hydro.app.core.prefs.PreferencesDataSource
import com.hydro.app.features.auth.data.AuthApi
import com.hydro.app.features.auth.data.AuthRepository
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/**
 * Модуль для авторизации.
 * 
 * AuthApi предоставляется через BackendApisModule.
 */
@Module
@InstallIn(SingletonComponent::class)
object AuthModule {
	@Provides
	@Singleton
	fun provideAuthRepository(
		api: AuthApi,
		prefs: PreferencesDataSource
	): AuthRepository {
		return AuthRepository(api, prefs)
	}
}


