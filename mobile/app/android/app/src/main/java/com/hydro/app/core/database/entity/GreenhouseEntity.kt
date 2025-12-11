package com.hydro.app.core.database.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "greenhouses")
data class GreenhouseEntity(
    @PrimaryKey val id: Int,
    val uid: String,
    val name: String,
    val location: String? = null,
    val status: String? = null,
    val zonesCount: Int? = null,
    val updatedAt: Long = System.currentTimeMillis()
)

