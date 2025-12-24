package com.hydro.app.core.domain.usecase

import com.hydro.app.core.data.ZonesRepository
import com.hydro.app.core.domain.AppError
import com.hydro.app.core.domain.AppResult
import com.hydro.app.core.domain.Validator
import com.hydro.app.core.domain.Zone
import com.hydro.app.core.domain.toAppError
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject

/**
 * Use Case для получения списка зон.
 */
class GetZonesUseCase @Inject constructor(
    private val repository: ZonesRepository
) {
    /**
     * Получает поток всех зон.
     */
    fun getAll(): Flow<List<Zone>> {
        return repository.getAll()
    }

    /**
     * Получает поток зон для конкретной теплицы.
     * 
     * @param greenhouseId ID теплицы
     * @return Flow со списком зон
     */
    fun getByGreenhouse(greenhouseId: Int): Flow<List<Zone>> {
        return repository.getByGreenhouse(greenhouseId)
    }

    /**
     * Получает зону по ID.
     * 
     * @param id ID зоны
     * @return Результат с зоной или ошибкой
     */
    suspend fun getById(id: Int): AppResult<Zone> {
        if (!Validator.isValidId(id)) {
            return Result.failure(
                AppError.ValidationError("Invalid zone ID", "id")
            )
        }

        return try {
            val zone = repository.getById(id)
            if (zone != null) {
                Result.success(zone)
            } else {
                Result.failure(AppError.UnknownError("Zone not found"))
            }
        } catch (e: Exception) {
            Result.failure(e.toAppError())
        }
    }

    /**
     * Обновляет список зон из API.
     * 
     * @param greenhouseId Опциональный ID теплицы для фильтрации
     * @return Результат операции
     */
    suspend fun refresh(greenhouseId: Int? = null): AppResult<Unit> {
        return try {
            repository.refresh(greenhouseId)
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e.toAppError())
        }
    }
}

