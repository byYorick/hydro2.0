package com.hydro.app.core.di

import android.content.Context
import androidx.room.Room
import com.hydro.app.core.database.HydroDatabase
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): HydroDatabase {
        return Room.databaseBuilder(
            context,
            HydroDatabase::class.java,
            "hydro_database"
        )
            .fallbackToDestructiveMigration()
            .build()
    }
}

