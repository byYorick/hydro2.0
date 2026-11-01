package com.hydro.app.features.auth.di

import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent

/**
 * AuthRepository и AuthApi связываются через constructor injection и BackendApisModule.
 */
@Module
@InstallIn(SingletonComponent::class)
object AuthModule
