package com.hydro.app.core.di

import android.content.Context
import com.hydro.app.core.config.ConfigLoader
import com.hydro.app.core.network.TokenProvider
import com.hydro.app.core.prefs.PreferencesDataSource
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import javax.inject.Named
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

	@Provides
	@Singleton
	fun provideConfigLoader(@ApplicationContext context: Context): ConfigLoader = ConfigLoader(context)

	@Provides
	@Singleton
	fun provideMoshi(): Moshi = Moshi.Builder()
		.addLast(KotlinJsonAdapterFactory())
		.build()

	@Provides
	@Singleton
	fun provideTokenProvider(prefs: PreferencesDataSource): TokenProvider = TokenProvider(prefs)

	@Provides
	@Singleton
	fun provideAuthInterceptor(tokenProvider: TokenProvider): Interceptor {
		return Interceptor { chain ->
			val original = chain.request()
			val token = tokenProvider.tokenState.value
			val request = if (!token.isNullOrBlank()) {
				original.newBuilder()
					.addHeader("Authorization", "Bearer $token")
					.addHeader("Accept", "application/json")
					.addHeader("Content-Type", "application/json")
					.build()
			} else {
				original.newBuilder()
					.addHeader("Accept", "application/json")
					.addHeader("Content-Type", "application/json")
					.build()
			}
			chain.proceed(request)
		}
	}

	@Provides
	@Singleton
	fun provideOkHttp(authInterceptor: Interceptor): OkHttpClient {
		val logging = HttpLoggingInterceptor().apply {
			level = if (com.hydro.app.BuildConfig.DEBUG) {
				HttpLoggingInterceptor.Level.BODY
			} else {
				HttpLoggingInterceptor.Level.BASIC
			}
		}
		return OkHttpClient.Builder()
			.addInterceptor(authInterceptor)
			.addInterceptor(logging)
			.build()
	}

	@Provides
	@Singleton
	@Named("baseUrl")
	fun provideBaseUrl(configLoader: ConfigLoader): String {
		return configLoader.loadConfig().apiBaseUrl
	}

	@Provides
	@Singleton
	fun provideRetrofit(
		okHttpClient: OkHttpClient,
		moshi: Moshi,
		@Named("baseUrl") baseUrl: String
	): Retrofit {
		return Retrofit.Builder()
			.baseUrl(baseUrl)
			.client(okHttpClient)
			.addConverterFactory(MoshiConverterFactory.create(moshi))
			.build()
	}
}


