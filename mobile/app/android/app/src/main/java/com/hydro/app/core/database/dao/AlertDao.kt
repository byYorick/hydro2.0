package com.hydro.app.core.database.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.hydro.app.core.database.entity.AlertEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface AlertDao {
    @Query("SELECT * FROM alerts ORDER BY timestamp DESC")
    fun getAll(): Flow<List<AlertEntity>>

    @Query("SELECT * FROM alerts WHERE status = :status ORDER BY timestamp DESC")
    fun getByStatus(status: String): Flow<List<AlertEntity>>

    @Query("SELECT * FROM alerts WHERE zoneId = :zoneId ORDER BY timestamp DESC")
    fun getByZone(zoneId: Int): Flow<List<AlertEntity>>

    @Query("SELECT * FROM alerts WHERE id = :id")
    suspend fun getById(id: Int): AlertEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(alerts: List<AlertEntity>)

    @Query("UPDATE alerts SET status = :status, acknowledgedAt = :acknowledgedAt WHERE id = :id")
    suspend fun acknowledge(id: Int, status: String, acknowledgedAt: String)

    @Query("DELETE FROM alerts WHERE timestamp < :before")
    suspend fun deleteOld(before: String)
}

