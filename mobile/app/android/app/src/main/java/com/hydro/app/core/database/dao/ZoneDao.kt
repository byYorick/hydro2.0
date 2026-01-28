package com.hydro.app.core.database.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.hydro.app.core.database.entity.ZoneEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface ZoneDao {
    @Query("SELECT * FROM zones WHERE greenhouseId = :greenhouseId ORDER BY name")
    fun getByGreenhouse(greenhouseId: Int): Flow<List<ZoneEntity>>

    @Query("SELECT * FROM zones WHERE id = :id")
    suspend fun getById(id: Int): ZoneEntity?

    @Query("SELECT * FROM zones ORDER BY name")
    fun getAll(): Flow<List<ZoneEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(zones: List<ZoneEntity>)

    @Query("DELETE FROM zones WHERE greenhouseId = :greenhouseId")
    suspend fun deleteByGreenhouse(greenhouseId: Int)

    @Query("DELETE FROM zones")
    suspend fun deleteAll()
}

