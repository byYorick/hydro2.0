package com.hydro.app.core.di

import android.content.Context
import com.hydro.app.core.auth.SessionManager
import com.hydro.app.core.i18n.AlertCatalog
import com.hydro.app.core.i18n.ErrorCatalog
import com.hydro.app.core.prefs.PreferencesDataSource
import com.squareup.moshi.Moshi
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {
	@Provides
	@Singleton
	fun providePreferences(@ApplicationContext context: Context): PreferencesDataSource {
		return PreferencesDataSource(context)
	}

	@Provides
	@Singleton
	fun provideSessionManager(prefs: PreferencesDataSource): SessionManager {
		return SessionManager(prefs)
	}

	@Provides
	@Singleton
	fun provideErrorCatalog(
		@ApplicationContext context: Context,
		moshi: Moshi,
	): ErrorCatalog = ErrorCatalog.load(context, moshi)

	@Provides
	@Singleton
	fun provideAlertCatalog(
		@ApplicationContext context: Context,
		moshi: Moshi,
	): AlertCatalog = AlertCatalog.load(context, moshi)
}


