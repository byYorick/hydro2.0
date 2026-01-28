<?php

namespace App\Database\Seeders;

use App\Contracts\Database\SeederInterface;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Log;

/**
 * Фабрика для управления сидерами и их зависимостями
 */
class SeederFactory
{
    /**
     * Экземпляры сидеров
     */
    private array $seeders = [];

    /**
     * Кеш результатов валидации зависимостей
     */
    private array $validationCache = [];

    /**
     * Создать экземпляр сидера
     */
    public function make(string $seederClass): SeederInterface
    {
        if (!isset($this->seeders[$seederClass])) {
            if (!class_exists($seederClass)) {
                throw new \InvalidArgumentException("Seeder class {$seederClass} does not exist");
            }

            $this->seeders[$seederClass] = app($seederClass);
        }

        return $this->seeders[$seederClass];
    }

    /**
     * Получить упорядоченный список сидеров с учетом зависимостей
     */
    public function getOrderedSeeders(array $seederClasses): Collection
    {
        $graph = $this->buildDependencyGraph($seederClasses);
        return $this->topologicalSort($graph);
    }

    /**
     * Проверить все зависимости для списка сидеров
     */
    public function validateAllDependencies(array $seederClasses): array
    {
        $results = [
            'valid' => [],
            'invalid' => [],
        ];

        foreach ($seederClasses as $seederClass) {
            try {
                $seeder = $this->make($seederClass);

                if ($seeder->validateDependencies()) {
                    $results['valid'][] = $seederClass;
                } else {
                    $results['invalid'][] = [
                        'seeder' => $seederClass,
                        'missing_dependencies' => $seeder->getDependencies(),
                    ];
                }
            } catch (\Throwable $e) {
                $results['invalid'][] = [
                    'seeder' => $seederClass,
                    'error' => $e->getMessage(),
                ];
            }
        }

        return $results;
    }

    /**
     * Построить граф зависимостей
     */
    private function buildDependencyGraph(array $seederClasses): array
    {
        $graph = [];

        foreach ($seederClasses as $seederClass) {
            $graph[$seederClass] = [];

            try {
                $seeder = $this->make($seederClass);
                $dependencies = $seeder->getDependencies();

                foreach ($dependencies as $dependency) {
                    if (in_array($dependency, $seederClasses)) {
                        $graph[$seederClass][] = $dependency;
                    }
                }
            } catch (\Throwable $e) {
                Log::warning("Failed to build dependency graph for {$seederClass}", [
                    'error' => $e->getMessage(),
                ]);
            }
        }

        return $graph;
    }

    /**
     * Топологическая сортировка графа зависимостей
     */
    private function topologicalSort(array $graph): Collection
    {
        $result = collect();
        $visited = [];
        $visiting = [];

        $visit = function ($node) use (&$visit, &$result, &$visited, &$visiting, $graph) {
            if (isset($visiting[$node])) {
                throw new \RuntimeException("Circular dependency detected involving {$node}");
            }

            if (!isset($visited[$node])) {
                $visiting[$node] = true;

                foreach ($graph[$node] ?? [] as $dependency) {
                    $visit($dependency);
                }

                $visiting[$node] = false;
                $visited[$node] = true;
                $result->push($node);
            }
        };

        foreach (array_keys($graph) as $node) {
            if (!isset($visited[$node])) {
                $visit($node);
            }
        }

        return $result;
    }

    /**
     * Получить информацию о сидере
     */
    public function getSeederInfo(string $seederClass): array
    {
        try {
            $seeder = $this->make($seederClass);

            return [
                'name' => $seeder->getSeederName(),
                'dependencies' => $seeder->getDependencies(),
                'dependencies_valid' => $seeder->validateDependencies(),
                'class' => $seederClass,
            ];
        } catch (\Throwable $e) {
            return [
                'name' => $seederClass,
                'error' => $e->getMessage(),
                'class' => $seederClass,
            ];
        }
    }

    /**
     * Очистить кеш
     */
    public function clearCache(): void
    {
        $this->seeders = [];
        $this->validationCache = [];
    }
}
