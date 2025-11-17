package com.hydro.app.core.di

import com.hydro.app.core.data.AlertsApi
import com.hydro.app.core.data.GreenhousesApi
import com.hydro.app.core.data.ZonesApi
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import retrofit2.Retrofit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object BackendApisModule {
	@Provides @Singleton fun provideGreenhousesApi(retrofit: Retrofit): GreenhousesApi =
		retrofit.create(GreenhousesApi::class.java)
	@Provides @Singleton fun provideZonesApi(retrofit: Retrofit): ZonesApi =
		retrofit.create(ZonesApi::class.java)
	@Provides @Singleton fun provideAlertsApi(retrofit: Retrofit): AlertsApi =
		retrofit.create(AlertsApi::class.java)
}


