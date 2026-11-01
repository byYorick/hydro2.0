package com.hydro.app.core.di

import com.hydro.app.BuildConfig
import com.hydro.app.core.config.CleartextPolicy
import com.hydro.app.core.config.ServerEndpointStore
import com.hydro.app.core.json.LenientNumberAdapters
import com.hydro.app.core.network.DynamicBaseUrlInterceptor
import com.hydro.app.core.network.TokenProvider
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideMoshi(): Moshi = Moshi.Builder()
        .add(LenientNumberAdapters)
        .addLast(KotlinJsonAdapterFactory())
        .build()

    @Provides
    @Singleton
    fun provideAuthInterceptor(tokenProvider: TokenProvider): Interceptor {
        return Interceptor { chain ->
            val token = tokenProvider.tokenState.value
            val builder = chain.request().newBuilder()
                .header("Accept", "application/json")
            if (!token.isNullOrBlank()) {
                builder.header("Authorization", "Bearer $token")
            }
            chain.proceed(builder.build())
        }
    }

    @Provides
    @Singleton
    fun provideDynamicBaseUrl(endpointStore: ServerEndpointStore): DynamicBaseUrlInterceptor {
        return DynamicBaseUrlInterceptor(
            endpointProvider = { endpointStore.current() },
            cleartextAllowed = { endpoint ->
                CleartextPolicy.allows(
                    endpoint = endpoint,
                    debugBuild = BuildConfig.DEBUG,
                    allowCleartextFlag = BuildConfig.ALLOW_CLEARTEXT,
                )
            },
        )
    }

    @Provides
    @Singleton
    fun provideOkHttp(
        authInterceptor: Interceptor,
        baseUrlInterceptor: DynamicBaseUrlInterceptor,
    ): OkHttpClient {
        val logging = HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) {
                HttpLoggingInterceptor.Level.BASIC
            } else {
                HttpLoggingInterceptor.Level.NONE
            }
            redactHeader("Authorization")
        }
        return OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .addInterceptor(baseUrlInterceptor)
            .addInterceptor(authInterceptor)
            .addInterceptor(logging)
            .build()
    }

    @Provides
    @Singleton
    fun provideRetrofit(okHttpClient: OkHttpClient, moshi: Moshi): Retrofit {
        return Retrofit.Builder()
            .baseUrl(DynamicBaseUrlInterceptor.PLACEHOLDER_BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
    }
}
