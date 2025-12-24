package com.hydro.app.core.database.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * Entity для хранения данных о теплице в Room database.
 * 
 * @property id Уникальный идентификатор теплицы
 * @property uid Уникальный строковый идентификатор
 * @property name Название теплицы
 * @property location Местоположение теплицы
 * @property status Статус теплицы
 * @property zonesCount Количество зон в теплице
 * @property updatedAt Время последнего обновления (timestamp)
 */
@Entity(
    tableName = "greenhouses",
    indices = [
        Index(value = ["uid"], unique = true),
        Index(value = ["name"]),
        Index(value = ["updatedAt"])
    ]
)
data class GreenhouseEntity(
    @PrimaryKey val id: Int,
    val uid: String,
    val name: String,
    val location: String? = null,
    val status: String? = null,
    val zonesCount: Int? = null,
    val updatedAt: Long = System.currentTimeMillis()
)

