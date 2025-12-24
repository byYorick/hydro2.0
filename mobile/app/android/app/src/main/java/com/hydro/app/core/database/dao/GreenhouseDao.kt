package com.hydro.app.core.database.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.hydro.app.core.database.entity.GreenhouseEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface GreenhouseDao {
    @Query("SELECT * FROM greenhouses ORDER BY name")
    fun getAll(): Flow<List<GreenhouseEntity>>

    @Query("SELECT * FROM greenhouses WHERE id = :id")
    suspend fun getById(id: Int): GreenhouseEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(greenhouses: List<GreenhouseEntity>)

    @Query("DELETE FROM greenhouses")
    suspend fun deleteAll()
}

