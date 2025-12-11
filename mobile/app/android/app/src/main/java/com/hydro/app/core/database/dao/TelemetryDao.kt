package com.hydro.app.core.database.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.hydro.app.core.database.entity.TelemetryEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface TelemetryDao {
    @Query("SELECT * FROM telemetry WHERE zoneId = :zoneId AND metric = :metric ORDER BY timestamp DESC LIMIT :limit")
    fun getHistory(zoneId: Int, metric: String, limit: Int = 1000): Flow<List<TelemetryEntity>>

    @Query("SELECT * FROM telemetry WHERE zoneId = :zoneId AND metric = :metric AND timestamp >= :from AND timestamp <= :to ORDER BY timestamp")
    fun getHistoryRange(zoneId: Int, metric: String, from: String, to: String): Flow<List<TelemetryEntity>>

    @Query("SELECT * FROM telemetry WHERE zoneId = :zoneId ORDER BY timestamp DESC LIMIT 1")
    suspend fun getLatest(zoneId: Int): TelemetryEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(telemetry: List<TelemetryEntity>)

    @Query("DELETE FROM telemetry WHERE zoneId = :zoneId AND metric = :metric AND timestamp < :before")
    suspend fun deleteOld(zoneId: Int, metric: String, before: String)

    @Query("DELETE FROM telemetry WHERE cachedAt < :before")
    suspend fun deleteOldByCacheTime(before: Long)
}

