package com.hydro.app.core.database.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.hydro.app.core.database.entity.NodeEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface NodeDao {
    @Query("SELECT * FROM nodes WHERE zoneId = :zoneId ORDER BY name")
    fun getByZone(zoneId: Int): Flow<List<NodeEntity>>

    @Query("SELECT * FROM nodes WHERE id = :id")
    suspend fun getById(id: Int): NodeEntity?

    @Query("SELECT * FROM nodes ORDER BY name")
    fun getAll(): Flow<List<NodeEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(nodes: List<NodeEntity>)

    @Query("DELETE FROM nodes WHERE zoneId = :zoneId")
    suspend fun deleteByZone(zoneId: Int)

    @Query("DELETE FROM nodes")
    suspend fun deleteAll()
}

