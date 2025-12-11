package com.hydro.app.core.database.entity

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "zones",
    foreignKeys = [
        ForeignKey(
            entity = GreenhouseEntity::class,
            parentColumns = ["id"],
            childColumns = ["greenhouseId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index("greenhouseId")]
)
data class ZoneEntity(
    @PrimaryKey val id: Int,
    val uid: String,
    val name: String,
    val greenhouseId: Int,
    val greenhouseUid: String? = null,
    val status: String? = null,
    val culture: String? = null,
    val recipeId: Int? = null,
    val recipeName: String? = null,
    val updatedAt: Long = System.currentTimeMillis()
)

