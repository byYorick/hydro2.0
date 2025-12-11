package com.hydro.app.core.database.entity

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "alerts",
    foreignKeys = [
        ForeignKey(
            entity = ZoneEntity::class,
            parentColumns = ["id"],
            childColumns = ["zoneId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index("zoneId"), Index("status"), Index("timestamp")]
)
data class AlertEntity(
    @PrimaryKey val id: Int,
    val level: String,
    val type: String,
    val zoneId: Int? = null,
    val zoneName: String? = null,
    val nodeId: Int? = null,
    val nodeName: String? = null,
    val message: String,
    val timestamp: String,
    val status: String? = null,
    val acknowledgedAt: String? = null,
    val updatedAt: Long = System.currentTimeMillis()
)

