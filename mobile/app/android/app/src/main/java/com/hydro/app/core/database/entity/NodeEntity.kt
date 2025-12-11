package com.hydro.app.core.database.entity

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "nodes",
    foreignKeys = [
        ForeignKey(
            entity = ZoneEntity::class,
            parentColumns = ["id"],
            childColumns = ["zoneId"],
            onDelete = ForeignKey.SET_NULL
        )
    ],
    indices = [Index("zoneId")]
)
data class NodeEntity(
    @PrimaryKey val id: Int,
    val uid: String,
    val name: String,
    val type: String,
    val status: String? = null,
    val zoneId: Int? = null,
    val zoneUid: String? = null,
    val rssi: Int? = null,
    val firmware: String? = null,
    val uptime: Long? = null,
    val updatedAt: Long = System.currentTimeMillis()
)

