<?php

namespace App\Database\Seeders;

use App\Contracts\Database\SeederInterface;
use Illuminate\Database\Seeder;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

/**
 * Базовый класс для всех сидеров системы
 * Предоставляет общую функциональность и паттерны
 */
abstract class BaseSeeder extends Seeder implements SeederInterface
{
    /**
     * Максимальное количество элементов для создания за раз
     */
    protected const BATCH_SIZE = 100;

    /**
     * Время ожидания между батчами в миллисекундах
     */
    protected const BATCH_DELAY_MS = 50;

    /**
     * Счетчик созданных элементов
     */
    protected int $createdCount = 0;

    /**
     * Счетчик обновленных элементов
     */
    protected int $updatedCount = 0;

    /**
     * Счетчик пропущенных элементов
     */
    protected int $skippedCount = 0;

    /**
     * Запуск сидера с улучшенным логированием
     */
    public function run(): void
    {
        $startTime = microtime(true);

        $this->command->info("🚀 Запуск сидера: {$this->getSeederName()}");

        try {
            // Проверка зависимостей
            if (! $this->validateDependencies()) {
                $this->command->error("❌ Зависимости не выполнены для сидера: {$this->getSeederName()}");
                $dependencies = $this->getDependencies();
                if (! empty($dependencies)) {
                    $this->command->error('Необходимые сидеры: '.implode(', ', $dependencies));
                }

                return;
            }

            // Выполнение сидера
            $this->execute();

            // Статистика выполнения
            $duration = round(microtime(true) - $startTime, 2);
            $this->logStatistics($duration);

        } catch (\Throwable $e) {
            $this->command->error("❌ Ошибка в сидере {$this->getSeederName()}: {$e->getMessage()}");
            Log::error("Seeder error: {$this->getSeederName()}", [
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
            ]);

            throw $e;
        }
    }

    /**
     * Основная логика сидера (должна быть реализована в наследниках)
     */
    abstract protected function execute(): void;

    /**
     * Проверка зависимостей по умолчанию
     */
    public function validateDependencies(): bool
    {
        $dependencies = $this->getDependencies();

        foreach ($dependencies as $dependency) {
            if (! $this->isSeederExecuted($dependency)) {
                return false;
            }
        }

        return true;
    }

    /**
     * Зависимости сидера (могут быть переопределены)
     */
    public function getDependencies(): array
    {
        return [];
    }

    /**
     * Очистка данных (должна быть реализована в наследниках)
     */
    public function cleanup(): void
    {
        $this->command->warn("🧹 Очистка не реализована для сидера: {$this->getSeederName()}");
    }

    /**
     * Имя сидера
     */
    public function getSeederName(): string
    {
        return static::class;
    }

    /**
     * Проверка, был ли сидер выполнен
     */
    protected function isSeederExecuted(string $seederClass): bool
    {
        // Простая проверка по имени класса
        $tableName = $this->getTableForSeeder($seederClass);

        if ($tableName) {
            return DB::table($tableName)->exists();
        }

        return true; // Если не можем проверить, считаем выполненным
    }

    /**
     * Получить имя таблицы для проверки сидера
     */
    protected function getTableForSeeder(string $seederClass): ?string
    {
        $mapping = [
            'PresetSeeder' => 'presets',
            'PlantTaxonomySeeder' => 'plants',
            'AdminUserSeeder' => 'users',
            'ExtendedUsersSeeder' => 'users',
            'ExtendedGreenhousesZonesSeeder' => 'zones',
            'ExtendedNodesChannelsSeeder' => 'nodes',
            'ExtendedRecipesCyclesSeeder' => 'recipes',
        ];

        return $mapping[$seederClass] ?? null;
    }

    /**
     * Создание элементов с прогресс-баром
     */
    protected function createWithProgress(Collection $items, callable $creator, string $itemName = 'элемент'): int
    {
        $total = $items->count();
        $bar = $this->command->getOutput()->createProgressBar($total);
        $bar->setFormat('verbose [%bar%] %percent:3s%% %elapsed:6s%/%estimated:-6s% %memory:6s%');

        $created = 0;
        $batch = collect();

        foreach ($items as $item) {
            $batch->push($item);

            if ($batch->count() >= static::BATCH_SIZE) {
                $created += $this->processBatch($batch, $creator, $bar);
                $batch = collect();

                // Небольшая пауза между батчами
                usleep(static::BATCH_DELAY_MS * 1000);
            }
        }

        // Обработка оставшихся элементов
        if ($batch->isNotEmpty()) {
            $created += $this->processBatch($batch, $creator, $bar);
        }

        $bar->finish();
        $this->command->newLine(2);

        return $created;
    }

    /**
     * Обработка батча элементов
     */
    protected function processBatch(Collection $batch, callable $creator, $bar): int
    {
        $created = 0;

        foreach ($batch as $item) {
            try {
                $result = $creator($item);

                if ($result === 'created') {
                    $created++;
                    $this->createdCount++;
                } elseif ($result === 'updated') {
                    $this->updatedCount++;
                } elseif ($result === 'skipped') {
                    $this->skippedCount++;
                }

                $bar->advance();
            } catch (\Throwable $e) {
                $this->command->error("Ошибка при обработке элемента: {$e->getMessage()}");
                Log::error("Batch processing error in {$this->getSeederName()}", [
                    'error' => $e->getMessage(),
                    'item' => $item,
                ]);
                $bar->advance();
            }
        }

        return $created;
    }

    /**
     * Безопасное создание или обновление записи
     */
    protected function firstOrCreate(string $model, array $attributes, array $values = []): mixed
    {
        try {
            $instance = $model::firstOrCreate($attributes, $values);

            if ($instance->wasRecentlyCreated) {
                return 'created';
            } else {
                // Обновляем все измененные поля, а не только первое совпадение.
                $changes = [];
                foreach ($values as $key => $value) {
                    if ($value != $instance->$key) {
                        $changes[$key] = $value;
                    }
                }

                if (! empty($changes)) {
                    $instance->update($changes);

                    return 'updated';
                }

                return 'skipped';
            }
        } catch (\Throwable $e) {
            Log::error("firstOrCreate failed in {$this->getSeederName()}", [
                'model' => $model,
                'attributes' => $attributes,
                'values' => $values,
                'error' => $e->getMessage(),
            ]);

            throw $e;
        }
    }

    /**
     * Создание коллекции элементов с валидацией
     */
    protected function createValidatedCollection(array $data, array $rules): Collection
    {
        $collection = collect();

        foreach ($data as $item) {
            if ($this->validateItem($item, $rules)) {
                $collection->push($item);
            } else {
                $this->command->warn('⚠️  Пропущен невалидный элемент: '.json_encode($item));
            }
        }

        return $collection;
    }

    /**
     * Валидация отдельного элемента
     */
    protected function validateItem(array $item, array $rules): bool
    {
        foreach ($rules as $field => $rule) {
            if (! isset($item[$field])) {
                return false;
            }

            if (is_callable($rule)) {
                if (! $rule($item[$field])) {
                    return false;
                }
            } elseif (is_array($rule)) {
                if (! in_array($item[$field], $rule)) {
                    return false;
                }
            } elseif ($rule === 'required' && empty($item[$field])) {
                return false;
            }
        }

        return true;
    }

    /**
     * Логирование статистики выполнения
     */
    protected function logStatistics(float $duration): void
    {
        $this->command->info("✅ Сидер {$this->getSeederName()} завершен за {$duration}s");
        $this->command->info("   📊 Создано: {$this->createdCount}");
        $this->command->info("   🔄 Обновлено: {$this->updatedCount}");
        $this->command->info("   ⏭️  Пропущено: {$this->skippedCount}");

        Log::info("Seeder completed: {$this->getSeederName()}", [
            'duration' => $duration,
            'created' => $this->createdCount,
            'updated' => $this->updatedCount,
            'skipped' => $this->skippedCount,
        ]);
    }

    /**
     * Генерация уникального UID
     */
    protected function generateUid(string $prefix = '', int $length = 8): string
    {
        return $prefix.Str::random($length);
    }

    /**
     * Генерация реалистичного email
     */
    protected function generateEmail(string $role, ?string $name = null): string
    {
        $name = $name ?? Str::slug($role);

        return "{$name}@hydro.local";
    }
}
