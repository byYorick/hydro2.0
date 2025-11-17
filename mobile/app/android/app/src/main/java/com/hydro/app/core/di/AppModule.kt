package com.hydro.app.core.di

import android.content.Context
import com.hydro.app.core.prefs.PreferencesDataSource
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
}


