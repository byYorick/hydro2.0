package com.hydro.app.core.di

import com.hydro.app.BuildConfig
import com.hydro.app.core.network.TokenProvider
import com.hydro.app.core.prefs.PreferencesDataSource
import com.squareup.moshi.Moshi
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
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
	fun provideMoshi(): Moshi = Moshi.Builder().build()

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
					.build()
			} else original
			chain.proceed(request)
		}
	}

	@Provides
	@Singleton
	fun provideOkHttp(authInterceptor: Interceptor): OkHttpClient {
		val logging = HttpLoggingInterceptor().apply {
			level = HttpLoggingInterceptor.Level.BASIC
		}
		return OkHttpClient.Builder()
			.addInterceptor(authInterceptor)
			.addInterceptor(logging)
			.build()
	}

	@Provides
	@Singleton
	@Named("baseUrl")
	fun provideBaseUrl(): String = BuildConfig.BACKEND_BASE_URL

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


