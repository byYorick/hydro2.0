<?php

namespace Database\Seeders;

use App\Models\GrowCycle;
use App\Models\GrowStageTemplate;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\NutrientProduct;
use App\Models\User;
use App\Models\Zone;
use App\Services\GrowCycleService;
use Illuminate\Database\Seeder;
use Illuminate\Support\Collection;
use Illuminate\Support\Str;

/**
 * Расширенный сидер для рецептов, фаз и циклов выращивания
 */
class ExtendedRecipesCyclesSeeder extends Seeder
{
    private array $nutrientProductIds = [];

    public function run(): void
    {
        $this->command->info('=== Создание расширенных рецептов и циклов ===');

        $this->seedNutrientProducts();
        $templates = $this->ensureStageTemplates();
        $revisions = $this->seedRecipes($templates);
        $this->seedGrowCycles($revisions);

        $this->command->info('Создано рецептов: '.Recipe::count());
        $this->command->info('Создано ревизий: '.RecipeRevision::count());
        $this->command->info('Создано фаз: '.RecipeRevisionPhase::count());
        $this->command->info('Создано циклов выращивания: '.GrowCycle::count());
    }

    private function ensureStageTemplates(): Collection
    {
        $templates = GrowStageTemplate::orderBy('order_index')->get();
        if ($templates->isNotEmpty()) {
            return $templates;
        }

        $stageTemplates = [
            [
                'name' => 'Посадка',
                'code' => 'PLANTING',
                'order_index' => 0,
                'default_duration_days' => 1,
                'ui_meta' => [
                    'color' => '#4CAF50',
                    'icon' => 'seedling',
                    'description' => 'Начальная стадия посадки семян или рассады',
                ],
            ],
            [
                'name' => 'Укоренение',
                'code' => 'ROOTING',
                'order_index' => 1,
                'default_duration_days' => 7,
                'ui_meta' => [
                    'color' => '#8BC34A',
                    'icon' => 'roots',
                    'description' => 'Стадия развития корневой системы',
                ],
            ],
            [
                'name' => 'Проращивание',
                'code' => 'GERMINATION',
                'order_index' => 2,
                'default_duration_days' => 3,
                'ui_meta' => [
                    'color' => '#CDDC39',
                    'icon' => 'sprout',
                    'description' => 'Стадия проращивания семян',
                ],
            ],
            [
                'name' => 'Вегетативная',
                'code' => 'VEG',
                'order_index' => 3,
                'default_duration_days' => 21,
                'ui_meta' => [
                    'color' => '#2196F3',
                    'icon' => 'leaf',
                    'description' => 'Стадия активного роста листьев и стеблей',
                ],
            ],
            [
                'name' => 'Цветение',
                'code' => 'FLOWER',
                'order_index' => 4,
                'default_duration_days' => 14,
                'ui_meta' => [
                    'color' => '#E91E63',
                    'icon' => 'flower',
                    'description' => 'Стадия цветения растений',
                ],
            ],
            [
                'name' => 'Плодоношение',
                'code' => 'FRUIT',
                'order_index' => 5,
                'default_duration_days' => 30,
                'ui_meta' => [
                    'color' => '#FF9800',
                    'icon' => 'fruit',
                    'description' => 'Стадия формирования и созревания плодов',
                ],
            ],
            [
                'name' => 'Сбор',
                'code' => 'HARVEST',
                'order_index' => 6,
                'default_duration_days' => 7,
                'ui_meta' => [
                    'color' => '#795548',
                    'icon' => 'harvest',
                    'description' => 'Стадия сбора урожая',
                ],
            ],
        ];

        foreach ($stageTemplates as $template) {
            GrowStageTemplate::firstOrCreate(
                ['code' => $template['code']],
                $template
            );
        }

        return GrowStageTemplate::orderBy('order_index')->get();
    }

    private function seedRecipes(Collection $templates): Collection
    {
        $revisions = collect();
        $recipeConfigs = $this->recipeConfigs();
        $createdBy = User::where('role', 'admin')->value('id') ?? User::value('id');
        $defaultRecipeByPlant = [];

        foreach ($recipeConfigs as $recipeConfig) {
            $plantSlugs = $recipeConfig['plant_slugs'] ?? [];
            $plants = Plant::query()->whereIn('slug', $plantSlugs)->get();

            if ($plants->isEmpty()) {
                $this->command->warn('Растения не найдены для рецепта: '.$recipeConfig['name']);
                continue;
            }

            $recipe = Recipe::firstOrCreate(
                ['name' => $recipeConfig['name']],
                [
                    'description' => $recipeConfig['description'],
                    'metadata' => [
                        'created_by' => 'system',
                        'version' => '1.0',
                        'crop_slugs' => $plantSlugs,
                        'source' => 'seed',
                    ],
                ]
            );

            $metadata = $recipe->metadata ?? [];
            if (empty($metadata['crop_slugs'])) {
                $metadata['crop_slugs'] = $plantSlugs;
            }
            $metadata['source'] = $metadata['source'] ?? 'seed';
            $metadata['version'] = $metadata['version'] ?? '1.0';
            $metadata['created_by'] = $metadata['created_by'] ?? 'system';

            if (! $recipe->description) {
                $recipe->description = $recipeConfig['description'];
            }

            $recipe->metadata = $metadata;
            $recipe->save();

            $pivotData = [];
            foreach ($plants as $plant) {
                $isDefault = empty($defaultRecipeByPlant[$plant->id]);
                $pivotData[$plant->id] = [
                    'season' => $recipeConfig['season'] ?? 'all_year',
                    'site_type' => $recipeConfig['site_type'] ?? 'indoor',
                    'is_default' => $isDefault,
                    'metadata' => json_encode([
                        'source' => 'seed',
                        'crop_slug' => $plant->slug,
                    ], JSON_UNESCAPED_UNICODE),
                ];
                $defaultRecipeByPlant[$plant->id] = true;
            }
            $recipe->plants()->syncWithoutDetaching($pivotData);

            $revision = RecipeRevision::firstOrCreate(
                [
                    'recipe_id' => $recipe->id,
                    'revision_number' => 1,
                ],
                [
                    'status' => 'PUBLISHED',
                    'description' => 'Автоматически созданная ревизия',
                    'created_by' => $createdBy,
                    'published_at' => now(),
                ]
            );

            foreach ($recipeConfig['phases'] as $phaseData) {
                $payload = $this->buildPhasePayload($recipe, $phaseData, $templates);

                RecipeRevisionPhase::updateOrCreate(
                    [
                        'recipe_revision_id' => $revision->id,
                        'phase_index' => $phaseData['phase_index'],
                    ],
                    $payload
                );
            }

            $revisions->push($revision->load('recipe.plants'));
        }

        return $revisions;
    }

    private function recipeConfigs(): array
    {
        return [
            [
                'name' => 'Томат тепличный (индет, интенсивный)',
                'description' => 'Высокоинтенсивный рецепт для индетерминантных томатов с контролем DLI и CO2.',
                'plant_slugs' => ['tomato'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 4, [
                        'ph' => ['min' => 5.6, 'max' => 6.0],
                        'ec' => ['min' => 0.6, 'max' => 1.0],
                        'temp_air' => ['min' => 24, 'max' => 27],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 6, 'max' => 10],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 150],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 900, 'duration_sec' => 20],
                        'mist' => ['interval_sec' => 600, 'duration_sec' => 15, 'mode' => 'SPRAY'],
                        'agronomy' => [
                            'critical_controls' => 'Стерильность субстрата, равномерная влажность, без переувлажнения.',
                            'risk_focus' => 'Корневая гниль, демпфинг-офф.',
                        ],
                    ]),
                    $this->phase(1, 'Рассада', 'ROOTING', 21, [
                        'ph' => ['min' => 5.7, 'max' => 6.2],
                        'ec' => ['min' => 1.2, 'max' => 1.8],
                        'temp_air' => ['min' => 22, 'max' => 25],
                        'humidity' => ['min' => 70, 'max' => 80],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 220],
                        'irrigation' => [
                            'mode' => 'SUBSTRATE',
                            'interval_sec' => 1800,
                            'duration_sec' => 45,
                            'drain_target_percent' => 10,
                        ],
                        'agronomy' => [
                            'nutrition_focus' => 'Азот/кальций для активного наращивания листа.',
                            'quality_check' => 'Толщина стебля, отсутствие вытягивания.',
                        ],
                    ]),
                    $this->phase(2, 'Вегетация', 'VEG', 28, [
                        'ph' => ['min' => 5.8, 'max' => 6.3],
                        'ec' => ['min' => 2.2, 'max' => 2.8],
                        'temp_air' => ['min' => 21, 'max' => 24],
                        'humidity' => ['min' => 65, 'max' => 75],
                        'co2' => ['min' => 800, 'max' => 1100],
                        'dli' => ['min' => 18, 'max' => 24],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 320],
                        'irrigation' => [
                            'mode' => 'SUBSTRATE',
                            'interval_sec' => 1200,
                            'duration_sec' => 75,
                            'drain_target_percent' => 20,
                            'drain_ec_target' => 2.6,
                        ],
                        'agronomy' => [
                            'training' => 'Ведение в 1 стебель, регулярное пасынкование.',
                            'critical_controls' => 'VPD 0.7–1.0 кПа, дренаж 15–25%.',
                        ],
                    ]),
                    $this->phase(3, 'Цветение и завязь', 'FLOWER', 21, [
                        'ph' => ['min' => 5.8, 'max' => 6.3],
                        'ec' => ['min' => 2.6, 'max' => 3.2],
                        'temp_air' => ['min' => 21, 'max' => 24],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 900, 'max' => 1200],
                        'dli' => ['min' => 20, 'max' => 26],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 360],
                        'irrigation' => [
                            'mode' => 'SUBSTRATE',
                            'interval_sec' => 1200,
                            'duration_sec' => 90,
                            'drain_target_percent' => 25,
                        ],
                        'agronomy' => [
                            'pollination' => 'Виброопыление или шмели 2–3 раза в неделю.',
                            'risk_focus' => 'Проблемы с завязью при высокой влажности.',
                        ],
                    ]),
                    $this->phase(4, 'Плодоношение', 'FRUIT', 42, [
                        'ph' => ['min' => 5.8, 'max' => 6.3],
                        'ec' => ['min' => 3.0, 'max' => 3.5],
                        'temp_air' => ['min' => 20, 'max' => 24],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 900, 'max' => 1200],
                        'dli' => ['min' => 20, 'max' => 26],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 360],
                        'irrigation' => [
                            'mode' => 'SUBSTRATE',
                            'interval_sec' => 1200,
                            'duration_sec' => 100,
                            'drain_target_percent' => 25,
                            'drain_ec_target' => 3.2,
                        ],
                        'agronomy' => [
                            'defoliation' => 'Удаление нижних листьев по мере налива кистей.',
                            'quality_check' => 'Контроль сахара/кислотности, равномерность окраски.',
                        ],
                    ]),
                ],
            ],
            [
                'name' => 'Томат тепличный (короткий оборот)',
                'description' => 'Укороченный цикл для детерминантных томатов с меньшей нагрузкой по DLI.',
                'plant_slugs' => ['tomato'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 4, [
                        'ph' => ['min' => 5.6, 'max' => 6.0],
                        'ec' => ['min' => 0.6, 'max' => 1.0],
                        'temp_air' => ['min' => 24, 'max' => 27],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 6, 'max' => 10],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 140],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 900, 'duration_sec' => 20],
                        'mist' => ['interval_sec' => 600, 'duration_sec' => 15, 'mode' => 'SPRAY'],
                    ]),
                    $this->phase(1, 'Рассада', 'ROOTING', 18, [
                        'ph' => ['min' => 5.7, 'max' => 6.2],
                        'ec' => ['min' => 1.2, 'max' => 1.7],
                        'temp_air' => ['min' => 22, 'max' => 24],
                        'humidity' => ['min' => 70, 'max' => 80],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 10, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 1800, 'duration_sec' => 45],
                    ]),
                    $this->phase(2, 'Вегетация', 'VEG', 21, [
                        'ph' => ['min' => 5.8, 'max' => 6.3],
                        'ec' => ['min' => 2.0, 'max' => 2.6],
                        'temp_air' => ['min' => 21, 'max' => 24],
                        'humidity' => ['min' => 65, 'max' => 75],
                        'co2' => ['min' => 800, 'max' => 1000],
                        'dli' => ['min' => 16, 'max' => 22],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 280],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 1500, 'duration_sec' => 75],
                    ]),
                    $this->phase(3, 'Плодоношение', 'FRUIT', 35, [
                        'ph' => ['min' => 5.8, 'max' => 6.3],
                        'ec' => ['min' => 2.6, 'max' => 3.2],
                        'temp_air' => ['min' => 20, 'max' => 23],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 800, 'max' => 1100],
                        'dli' => ['min' => 18, 'max' => 24],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 320],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 1500, 'duration_sec' => 90],
                        'agronomy' => [
                            'critical_controls' => 'Контроль равномерности питания, избегать стрессов по влаге.',
                        ],
                    ]),
                ],
            ],
            [
                'name' => 'Огурец партенокарпический',
                'description' => 'Рецепт для партенокарпических огурцов с акцентом на влажность и стабильный дренаж.',
                'plant_slugs' => ['cucumber'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 3, [
                        'ph' => ['min' => 5.5, 'max' => 6.0],
                        'ec' => ['min' => 0.6, 'max' => 1.0],
                        'temp_air' => ['min' => 26, 'max' => 28],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 8, 'max' => 12],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 180],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 900, 'duration_sec' => 20],
                        'mist' => ['interval_sec' => 600, 'duration_sec' => 15, 'mode' => 'SPRAY'],
                    ]),
                    $this->phase(1, 'Рассада', 'ROOTING', 10, [
                        'ph' => ['min' => 5.6, 'max' => 6.1],
                        'ec' => ['min' => 1.2, 'max' => 1.8],
                        'temp_air' => ['min' => 24, 'max' => 26],
                        'humidity' => ['min' => 75, 'max' => 85],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 240],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 1800, 'duration_sec' => 45],
                    ]),
                    $this->phase(2, 'Вегетация', 'VEG', 18, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 1.8, 'max' => 2.4],
                        'temp_air' => ['min' => 22, 'max' => 25],
                        'humidity' => ['min' => 70, 'max' => 80],
                        'co2' => ['min' => 800, 'max' => 1100],
                        'dli' => ['min' => 16, 'max' => 22],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 320],
                        'irrigation' => [
                            'mode' => 'SUBSTRATE',
                            'interval_sec' => 1200,
                            'duration_sec' => 75,
                            'drain_target_percent' => 20,
                        ],
                        'agronomy' => [
                            'training' => 'Удаление боковых побегов до 5–6 узла, формирование.',
                        ],
                    ]),
                    $this->phase(3, 'Плодоношение', 'FRUIT', 28, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 2.4, 'max' => 2.8],
                        'temp_air' => ['min' => 21, 'max' => 24],
                        'humidity' => ['min' => 70, 'max' => 80],
                        'co2' => ['min' => 900, 'max' => 1200],
                        'dli' => ['min' => 18, 'max' => 24],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 340],
                        'irrigation' => [
                            'mode' => 'SUBSTRATE',
                            'interval_sec' => 1200,
                            'duration_sec' => 90,
                            'drain_target_percent' => 25,
                        ],
                        'agronomy' => [
                            'critical_controls' => 'Стабильность влажности субстрата, контроль кривизны плодов.',
                        ],
                    ]),
                ],
            ],
            [
                'name' => 'Клубника нейтрального дня',
                'description' => 'Интенсивный рецепт для ремонтантной клубники с контролем фотопериода.',
                'plant_slugs' => ['strawberry'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Укоренение', 'ROOTING', 14, [
                        'ph' => ['min' => 5.4, 'max' => 6.0],
                        'ec' => ['min' => 0.8, 'max' => 1.2],
                        'temp_air' => ['min' => 18, 'max' => 21],
                        'humidity' => ['min' => 80, 'max' => 90],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 8, 'max' => 12],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 1800, 'duration_sec' => 45],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 21, [
                        'ph' => ['min' => 5.5, 'max' => 6.2],
                        'ec' => ['min' => 1.2, 'max' => 1.6],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 65, 'max' => 75],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 1500, 'duration_sec' => 60],
                    ]),
                    $this->phase(2, 'Цветение', 'FLOWER', 21, [
                        'ph' => ['min' => 5.5, 'max' => 6.2],
                        'ec' => ['min' => 1.4, 'max' => 1.8],
                        'temp_air' => ['min' => 17, 'max' => 21],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 700, 'max' => 900],
                        'dli' => ['min' => 14, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 280],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 1500, 'duration_sec' => 75],
                        'agronomy' => [
                            'pollination' => 'Виброопыление или шмели.',
                            'risk_focus' => 'Серая гниль при повышенной влажности.',
                        ],
                    ]),
                    $this->phase(3, 'Плодоношение', 'FRUIT', 35, [
                        'ph' => ['min' => 5.5, 'max' => 6.2],
                        'ec' => ['min' => 1.5, 'max' => 1.9],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 700, 'max' => 900],
                        'dli' => ['min' => 14, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 280],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 1500, 'duration_sec' => 75],
                        'agronomy' => [
                            'quality_check' => 'Контроль сахара/кислотности, плотность ягоды.',
                        ],
                    ]),
                ],
            ],
            [
                'name' => 'Голубика (кислый субстрат)',
                'description' => 'Рецепт для голубики с кислотной зоной корней и умеренной EC.',
                'plant_slugs' => ['blueberry'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Адаптация', 'ROOTING', 21, [
                        'ph' => ['min' => 4.5, 'max' => 5.2],
                        'ec' => ['min' => 0.8, 'max' => 1.2],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 70, 'max' => 85],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                        'agronomy' => [
                            'critical_controls' => 'Стабильный pH 4.5–5.2, избегать засоления.',
                        ],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 28, [
                        'ph' => ['min' => 4.5, 'max' => 5.2],
                        'ec' => ['min' => 1.0, 'max' => 1.6],
                        'temp_air' => ['min' => 18, 'max' => 24],
                        'humidity' => ['min' => 65, 'max' => 75],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                    $this->phase(2, 'Цветение', 'FLOWER', 21, [
                        'ph' => ['min' => 4.5, 'max' => 5.2],
                        'ec' => ['min' => 1.0, 'max' => 1.6],
                        'temp_air' => ['min' => 16, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                    $this->phase(3, 'Плодоношение', 'FRUIT', 42, [
                        'ph' => ['min' => 4.5, 'max' => 5.2],
                        'ec' => ['min' => 1.0, 'max' => 1.6],
                        'temp_air' => ['min' => 16, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                ],
            ],
            [
                'name' => 'Малина ремонтантная',
                'description' => 'Рецепт для малины с контролем дренажа и умеренной EC.',
                'plant_slugs' => ['raspberry'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Укоренение', 'ROOTING', 21, [
                        'ph' => ['min' => 5.5, 'max' => 6.2],
                        'ec' => ['min' => 1.0, 'max' => 1.4],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 70, 'max' => 85],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 28, [
                        'ph' => ['min' => 5.6, 'max' => 6.4],
                        'ec' => ['min' => 1.4, 'max' => 2.0],
                        'temp_air' => ['min' => 18, 'max' => 24],
                        'humidity' => ['min' => 65, 'max' => 75],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 14, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                    $this->phase(2, 'Цветение', 'FLOWER', 21, [
                        'ph' => ['min' => 5.6, 'max' => 6.4],
                        'ec' => ['min' => 1.6, 'max' => 2.2],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 14, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                    $this->phase(3, 'Плодоношение', 'FRUIT', 35, [
                        'ph' => ['min' => 5.6, 'max' => 6.4],
                        'ec' => ['min' => 1.6, 'max' => 2.2],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 14, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                ],
            ],
            [
                'name' => 'Ежевика тепличная',
                'description' => 'Рецепт для ежевики с умеренными температурами и стабильным pH.',
                'plant_slugs' => ['blackberry'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Укоренение', 'ROOTING', 21, [
                        'ph' => ['min' => 5.5, 'max' => 6.3],
                        'ec' => ['min' => 1.0, 'max' => 1.4],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 70, 'max' => 85],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 28, [
                        'ph' => ['min' => 5.6, 'max' => 6.4],
                        'ec' => ['min' => 1.4, 'max' => 2.0],
                        'temp_air' => ['min' => 18, 'max' => 24],
                        'humidity' => ['min' => 65, 'max' => 75],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 14, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                    $this->phase(2, 'Цветение', 'FLOWER', 21, [
                        'ph' => ['min' => 5.6, 'max' => 6.4],
                        'ec' => ['min' => 1.6, 'max' => 2.2],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 14, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                    $this->phase(3, 'Плодоношение', 'FRUIT', 35, [
                        'ph' => ['min' => 5.6, 'max' => 6.4],
                        'ec' => ['min' => 1.6, 'max' => 2.2],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 14, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                ],
            ],
            [
                'name' => 'Перец сладкий',
                'description' => 'Рецепт для сладкого перца с повышенной температурой и контролем EC.',
                'plant_slugs' => ['pepper-sweet'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 6, [
                        'ph' => ['min' => 5.7, 'max' => 6.2],
                        'ec' => ['min' => 0.8, 'max' => 1.2],
                        'temp_air' => ['min' => 26, 'max' => 28],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 8, 'max' => 12],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 180],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 900, 'duration_sec' => 20],
                        'mist' => ['interval_sec' => 600, 'duration_sec' => 15, 'mode' => 'SPRAY'],
                    ]),
                    $this->phase(1, 'Рассада', 'ROOTING', 21, [
                        'ph' => ['min' => 5.8, 'max' => 6.4],
                        'ec' => ['min' => 1.4, 'max' => 2.0],
                        'temp_air' => ['min' => 23, 'max' => 26],
                        'humidity' => ['min' => 70, 'max' => 80],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 1800, 'duration_sec' => 60],
                    ]),
                    $this->phase(2, 'Вегетация', 'VEG', 28, [
                        'ph' => ['min' => 5.8, 'max' => 6.5],
                        'ec' => ['min' => 2.2, 'max' => 2.8],
                        'temp_air' => ['min' => 22, 'max' => 25],
                        'humidity' => ['min' => 60, 'max' => 75],
                        'co2' => ['min' => 800, 'max' => 1100],
                        'dli' => ['min' => 18, 'max' => 24],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 320],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 1500, 'duration_sec' => 90],
                    ]),
                    $this->phase(3, 'Плодоношение', 'FRUIT', 42, [
                        'ph' => ['min' => 5.8, 'max' => 6.5],
                        'ec' => ['min' => 2.6, 'max' => 3.2],
                        'temp_air' => ['min' => 21, 'max' => 24],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 800, 'max' => 1100],
                        'dli' => ['min' => 18, 'max' => 24],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 320],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 1500, 'duration_sec' => 90],
                    ]),
                ],
            ],
            [
                'name' => 'Баклажан тепличный',
                'description' => 'Рецепт для баклажана с высокими температурами и повышенной EC.',
                'plant_slugs' => ['eggplant'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 6, [
                        'ph' => ['min' => 5.7, 'max' => 6.2],
                        'ec' => ['min' => 0.8, 'max' => 1.2],
                        'temp_air' => ['min' => 26, 'max' => 28],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 8, 'max' => 12],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 180],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 900, 'duration_sec' => 20],
                        'mist' => ['interval_sec' => 600, 'duration_sec' => 15, 'mode' => 'SPRAY'],
                    ]),
                    $this->phase(1, 'Рассада', 'ROOTING', 21, [
                        'ph' => ['min' => 5.8, 'max' => 6.4],
                        'ec' => ['min' => 1.6, 'max' => 2.2],
                        'temp_air' => ['min' => 24, 'max' => 27],
                        'humidity' => ['min' => 70, 'max' => 80],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 1800, 'duration_sec' => 60],
                    ]),
                    $this->phase(2, 'Вегетация', 'VEG', 28, [
                        'ph' => ['min' => 5.8, 'max' => 6.5],
                        'ec' => ['min' => 2.4, 'max' => 3.0],
                        'temp_air' => ['min' => 24, 'max' => 28],
                        'humidity' => ['min' => 60, 'max' => 75],
                        'co2' => ['min' => 800, 'max' => 1100],
                        'dli' => ['min' => 18, 'max' => 24],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 320],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 1500, 'duration_sec' => 90],
                    ]),
                    $this->phase(3, 'Плодоношение', 'FRUIT', 42, [
                        'ph' => ['min' => 5.8, 'max' => 6.5],
                        'ec' => ['min' => 2.8, 'max' => 3.5],
                        'temp_air' => ['min' => 23, 'max' => 27],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 800, 'max' => 1100],
                        'dli' => ['min' => 18, 'max' => 24],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 320],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 1500, 'duration_sec' => 90],
                    ]),
                ],
            ],
            [
                'name' => 'Горох овощной',
                'description' => 'Рецепт для гороха с прохладным климатом и умеренной EC.',
                'plant_slugs' => ['peas'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 5, [
                        'ph' => ['min' => 5.8, 'max' => 6.4],
                        'ec' => ['min' => 1.0, 'max' => 1.4],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 75, 'max' => 85],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 1200, 'duration_sec' => 120],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 21, [
                        'ph' => ['min' => 5.8, 'max' => 6.5],
                        'ec' => ['min' => 1.2, 'max' => 1.8],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 60, 'max' => 75],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 240],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 1200, 'duration_sec' => 150],
                    ]),
                    $this->phase(2, 'Цветение', 'FLOWER', 14, [
                        'ph' => ['min' => 5.8, 'max' => 6.5],
                        'ec' => ['min' => 1.4, 'max' => 2.0],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 240],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 1200, 'duration_sec' => 150],
                    ]),
                    $this->phase(3, 'Налив бобов', 'FRUIT', 21, [
                        'ph' => ['min' => 5.8, 'max' => 6.5],
                        'ec' => ['min' => 1.4, 'max' => 2.0],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 240],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 1200, 'duration_sec' => 150],
                    ]),
                ],
            ],
            [
                'name' => 'Салат листовой (стандарт)',
                'description' => 'Классический рецепт для листового салата с умеренным DLI.',
                'plant_slugs' => ['lettuce'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 3, [
                        'ph' => ['min' => 5.5, 'max' => 6.0],
                        'ec' => ['min' => 0.6, 'max' => 0.9],
                        'temp_air' => ['min' => 18, 'max' => 21],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 6, 'max' => 10],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 160],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 120],
                    ]),
                    $this->phase(1, 'Рассада', 'ROOTING', 10, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 0.8, 'max' => 1.2],
                        'temp_air' => ['min' => 18, 'max' => 21],
                        'humidity' => ['min' => 70, 'max' => 80],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 120],
                    ]),
                    $this->phase(2, 'Вегетация', 'VEG', 18, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 1.2, 'max' => 1.6],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 240],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                        'agronomy' => [
                            'critical_controls' => 'Предотвратить tip-burn: кальций, влажность 60–70%.',
                        ],
                    ]),
                    $this->phase(3, 'Сбор', 'HARVEST', 7, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 1.0, 'max' => 1.4],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                ],
            ],
            [
                'name' => 'Салат листовой (ускоренный оборот)',
                'description' => 'Ускоренный цикл салата с повышенным DLI и питанием.',
                'plant_slugs' => ['lettuce'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 2, [
                        'ph' => ['min' => 5.5, 'max' => 6.0],
                        'ec' => ['min' => 0.6, 'max' => 0.9],
                        'temp_air' => ['min' => 19, 'max' => 22],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 8, 'max' => 12],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 120],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 16, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 1.4, 'max' => 1.8],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 14, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                        'agronomy' => [
                            'critical_controls' => 'Контроль tip-burn: кальций, VPD 0.6–0.8.',
                        ],
                    ]),
                    $this->phase(2, 'Сбор', 'HARVEST', 6, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 1.2, 'max' => 1.6],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 240],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                ],
            ],
            [
                'name' => 'Салат Айсберг',
                'description' => 'Рецепт для Айсберга с длительным формированием кочана.',
                'plant_slugs' => ['lettuce-iceberg'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 3, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 0.8, 'max' => 1.2],
                        'temp_air' => ['min' => 16, 'max' => 19],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 6, 'max' => 10],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 160],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 120],
                    ]),
                    $this->phase(1, 'Рассада', 'ROOTING', 10, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 1.0, 'max' => 1.4],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 70, 'max' => 80],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 120],
                    ]),
                    $this->phase(2, 'Формирование кочана', 'VEG', 28, [
                        'ph' => ['min' => 5.7, 'max' => 6.2],
                        'ec' => ['min' => 1.4, 'max' => 1.8],
                        'temp_air' => ['min' => 14, 'max' => 20],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                    $this->phase(3, 'Сбор', 'HARVEST', 7, [
                        'ph' => ['min' => 5.7, 'max' => 6.2],
                        'ec' => ['min' => 1.2, 'max' => 1.6],
                        'temp_air' => ['min' => 14, 'max' => 18],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                ],
            ],
            [
                'name' => 'Руккола',
                'description' => 'Рецепт для рукколы с быстрым оборотом и умеренным питанием.',
                'plant_slugs' => ['arugula'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 3, [
                        'ph' => ['min' => 5.5, 'max' => 6.2],
                        'ec' => ['min' => 0.8, 'max' => 1.2],
                        'temp_air' => ['min' => 18, 'max' => 21],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 8, 'max' => 12],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 180],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 120],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 16, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.2, 'max' => 1.6],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                    $this->phase(2, 'Сбор', 'HARVEST', 5, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.0, 'max' => 1.4],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                ],
            ],
            [
                'name' => 'Пекинская капуста',
                'description' => 'Рецепт для пекинской капусты с умеренной температурой и высоким DLI.',
                'plant_slugs' => ['chinese-cabbage'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 4, [
                        'ph' => ['min' => 5.5, 'max' => 6.2],
                        'ec' => ['min' => 0.8, 'max' => 1.2],
                        'temp_air' => ['min' => 18, 'max' => 21],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 8, 'max' => 12],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 180],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 120],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 21, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.6, 'max' => 2.2],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 75],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 240],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                    $this->phase(2, 'Формирование кочана', 'VEG', 21, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.8, 'max' => 2.4],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 240],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                    $this->phase(3, 'Сбор', 'HARVEST', 7, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.4, 'max' => 2.0],
                        'temp_air' => ['min' => 16, 'max' => 18],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                ],
            ],
            [
                'name' => 'Шпинат',
                'description' => 'Рецепт для шпината с прохладной температурой и повышенной EC.',
                'plant_slugs' => ['spinach'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 4, [
                        'ph' => ['min' => 5.8, 'max' => 6.4],
                        'ec' => ['min' => 1.2, 'max' => 1.6],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 8, 'max' => 12],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 160],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 120],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 21, [
                        'ph' => ['min' => 5.8, 'max' => 6.5],
                        'ec' => ['min' => 1.8, 'max' => 2.3],
                        'temp_air' => ['min' => 14, 'max' => 18],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                    $this->phase(2, 'Сбор', 'HARVEST', 7, [
                        'ph' => ['min' => 5.8, 'max' => 6.5],
                        'ec' => ['min' => 1.6, 'max' => 2.0],
                        'temp_air' => ['min' => 12, 'max' => 16],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 180],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                ],
            ],
            [
                'name' => 'Кейл',
                'description' => 'Рецепт для кейла с умеренной температурой и стабильной EC.',
                'plant_slugs' => ['kale'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 4, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 0.8, 'max' => 1.2],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 8, 'max' => 12],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 180],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 120],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 28, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.8, 'max' => 2.4],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                    $this->phase(2, 'Сбор', 'HARVEST', 7, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.6, 'max' => 2.0],
                        'temp_air' => ['min' => 14, 'max' => 18],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                ],
            ],
            [
                'name' => 'Мангольд',
                'description' => 'Рецепт для мангольда с умеренными температурами и стабильной EC.',
                'plant_slugs' => ['chard'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 5, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 0.8, 'max' => 1.2],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 8, 'max' => 12],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 180],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 120],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 28, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.8, 'max' => 2.3],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                    $this->phase(2, 'Сбор', 'HARVEST', 7, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.6, 'max' => 2.0],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                ],
            ],
            [
                'name' => 'Укроп',
                'description' => 'Рецепт для укропа с умеренной температурой и низкой EC.',
                'plant_slugs' => ['dill'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 5, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 0.8, 'max' => 1.2],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 8, 'max' => 12],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 180],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 120],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 21, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.2, 'max' => 1.8],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                    $this->phase(2, 'Сбор', 'HARVEST', 7, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.0, 'max' => 1.4],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                ],
            ],
            [
                'name' => 'Петрушка',
                'description' => 'Рецепт для петрушки с длительной вегетацией.',
                'plant_slugs' => ['parsley'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 7, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 0.8, 'max' => 1.2],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 8, 'max' => 12],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 180],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 120],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 28, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.4, 'max' => 2.0],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                    $this->phase(2, 'Сбор', 'HARVEST', 7, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.2, 'max' => 1.6],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                ],
            ],
            [
                'name' => 'Кинза',
                'description' => 'Рецепт для кинзы с умеренным питанием и контролем стрелкования.',
                'plant_slugs' => ['cilantro'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 7, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 0.8, 'max' => 1.2],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 8, 'max' => 12],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 180],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 120],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 21, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.2, 'max' => 1.8],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                        'agronomy' => [
                            'critical_controls' => 'Не перегревать, чтобы избежать стрелкования.',
                        ],
                    ]),
                    $this->phase(2, 'Сбор', 'HARVEST', 7, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.0, 'max' => 1.4],
                        'temp_air' => ['min' => 16, 'max' => 20],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                ],
            ],
            [
                'name' => 'Мята',
                'description' => 'Рецепт для мяты с акцентом на чистоту и стабильную влажность субстрата.',
                'plant_slugs' => ['mint'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Укоренение', 'ROOTING', 10, [
                        'ph' => ['min' => 5.6, 'max' => 6.2],
                        'ec' => ['min' => 1.0, 'max' => 1.4],
                        'temp_air' => ['min' => 20, 'max' => 24],
                        'humidity' => ['min' => 75, 'max' => 85],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 200],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 1200, 'duration_sec' => 120],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 21, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.4, 'max' => 2.0],
                        'temp_air' => ['min' => 18, 'max' => 24],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 1200, 'duration_sec' => 150],
                    ]),
                    $this->phase(2, 'Сбор', 'HARVEST', 7, [
                        'ph' => ['min' => 5.6, 'max' => 6.5],
                        'ec' => ['min' => 1.2, 'max' => 1.6],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 12, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 16, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 1200, 'duration_sec' => 150],
                    ]),
                ],
            ],
            [
                'name' => 'Базилик (Генуэзский)',
                'description' => 'Базовый рецепт для базилика с акцентом на ароматические масла.',
                'plant_slugs' => ['basil-genovese'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Проращивание', 'GERMINATION', 4, [
                        'ph' => ['min' => 5.5, 'max' => 6.2],
                        'ec' => ['min' => 0.8, 'max' => 1.2],
                        'temp_air' => ['min' => 22, 'max' => 26],
                        'humidity' => ['min' => 85, 'max' => 95],
                        'co2' => ['min' => 400, 'max' => 700],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 120],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 21, [
                        'ph' => ['min' => 5.6, 'max' => 6.4],
                        'ec' => ['min' => 1.4, 'max' => 1.8],
                        'temp_air' => ['min' => 20, 'max' => 26],
                        'humidity' => ['min' => 55, 'max' => 70],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 14, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                        'agronomy' => [
                            'quality_check' => 'Контроль эфирных масел: не перегревать.',
                        ],
                    ]),
                    $this->phase(2, 'Сбор', 'HARVEST', 7, [
                        'ph' => ['min' => 5.6, 'max' => 6.4],
                        'ec' => ['min' => 1.2, 'max' => 1.6],
                        'temp_air' => ['min' => 20, 'max' => 24],
                        'humidity' => ['min' => 55, 'max' => 70],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 16],
                        'lighting' => ['photoperiod_hours' => 18, 'ppfd' => 240],
                        'irrigation' => ['mode' => 'RECIRC', 'interval_sec' => 900, 'duration_sec' => 150],
                    ]),
                ],
            ],
            [
                'name' => 'Смородина черная',
                'description' => 'Рецепт для черной смородины с умеренным питанием и стабильным климатом.',
                'plant_slugs' => ['currant-black'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Укоренение', 'ROOTING', 21, [
                        'ph' => ['min' => 5.5, 'max' => 6.2],
                        'ec' => ['min' => 1.0, 'max' => 1.4],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 70, 'max' => 85],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 28, [
                        'ph' => ['min' => 5.6, 'max' => 6.4],
                        'ec' => ['min' => 1.4, 'max' => 2.0],
                        'temp_air' => ['min' => 18, 'max' => 24],
                        'humidity' => ['min' => 65, 'max' => 75],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                    $this->phase(2, 'Цветение', 'FLOWER', 21, [
                        'ph' => ['min' => 5.6, 'max' => 6.4],
                        'ec' => ['min' => 1.6, 'max' => 2.2],
                        'temp_air' => ['min' => 16, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                    $this->phase(3, 'Плодоношение', 'FRUIT', 35, [
                        'ph' => ['min' => 5.6, 'max' => 6.4],
                        'ec' => ['min' => 1.6, 'max' => 2.2],
                        'temp_air' => ['min' => 16, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                ],
            ],
            [
                'name' => 'Крыжовник',
                'description' => 'Рецепт для крыжовника с умеренным питанием и контролем влажности.',
                'plant_slugs' => ['gooseberry'],
                'season' => 'all_year',
                'site_type' => 'indoor',
                'phases' => [
                    $this->phase(0, 'Укоренение', 'ROOTING', 21, [
                        'ph' => ['min' => 5.5, 'max' => 6.2],
                        'ec' => ['min' => 1.0, 'max' => 1.4],
                        'temp_air' => ['min' => 18, 'max' => 22],
                        'humidity' => ['min' => 70, 'max' => 85],
                        'co2' => ['min' => 500, 'max' => 800],
                        'dli' => ['min' => 10, 'max' => 14],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 220],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                    $this->phase(1, 'Вегетация', 'VEG', 28, [
                        'ph' => ['min' => 5.6, 'max' => 6.4],
                        'ec' => ['min' => 1.4, 'max' => 2.0],
                        'temp_air' => ['min' => 18, 'max' => 24],
                        'humidity' => ['min' => 65, 'max' => 75],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                    $this->phase(2, 'Цветение', 'FLOWER', 21, [
                        'ph' => ['min' => 5.6, 'max' => 6.4],
                        'ec' => ['min' => 1.6, 'max' => 2.2],
                        'temp_air' => ['min' => 16, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                    $this->phase(3, 'Плодоношение', 'FRUIT', 35, [
                        'ph' => ['min' => 5.6, 'max' => 6.4],
                        'ec' => ['min' => 1.6, 'max' => 2.2],
                        'temp_air' => ['min' => 16, 'max' => 22],
                        'humidity' => ['min' => 60, 'max' => 70],
                        'co2' => ['min' => 600, 'max' => 900],
                        'dli' => ['min' => 12, 'max' => 18],
                        'lighting' => ['photoperiod_hours' => 14, 'ppfd' => 260],
                        'irrigation' => ['mode' => 'SUBSTRATE', 'interval_sec' => 2400, 'duration_sec' => 90],
                    ]),
                ],
            ],
        ];
    }

    private function phase(int $index, string $name, string $stageCode, int $durationDays, array $data = []): array
    {
        return array_merge([
            'phase_index' => $index,
            'name' => $name,
            'stage_code' => $stageCode,
            'duration_days' => $durationDays,
            'progress_model' => $data['progress_model'] ?? 'TIME',
        ], $data);
    }

    private function buildPhasePayload(Recipe $recipe, array $phaseData, Collection $templates): array
    {
        $stageTemplate = $this->resolveStageTemplate($recipe, $phaseData, $templates);

        $ph = $phaseData['ph'] ?? [];
        $ec = $phaseData['ec'] ?? [];
        $tempAir = $phaseData['temp_air'] ?? [];
        $humidity = $phaseData['humidity'] ?? [];
        $co2 = $phaseData['co2'] ?? [];
        $dli = $phaseData['dli'] ?? [];
        $lighting = $phaseData['lighting'] ?? [];
        $irrigation = $phaseData['irrigation'] ?? [];
        $mist = $phaseData['mist'] ?? [];

        $phMin = $phaseData['ph_min'] ?? $ph['min'] ?? null;
        $phMax = $phaseData['ph_max'] ?? $ph['max'] ?? null;
        $phTarget = $phaseData['ph_target'] ?? $ph['target'] ?? $this->averageTarget(['min' => $phMin, 'max' => $phMax]);

        $ecMin = $phaseData['ec_min'] ?? $ec['min'] ?? null;
        $ecMax = $phaseData['ec_max'] ?? $ec['max'] ?? null;
        $ecTarget = $phaseData['ec_target'] ?? $ec['target'] ?? $this->averageTarget(['min' => $ecMin, 'max' => $ecMax]);
        $nutritionProfile = $this->buildNutritionProfile(
            $phaseData,
            $phaseData['stage_code'] ?? $stageTemplate?->code
        );

        $tempMin = $phaseData['temp_air_min'] ?? $tempAir['min'] ?? null;
        $tempMax = $phaseData['temp_air_max'] ?? $tempAir['max'] ?? null;
        $tempTarget = $phaseData['temp_air_target'] ?? $tempAir['target'] ?? $this->averageTarget(['min' => $tempMin, 'max' => $tempMax]);

        $humidityMin = $phaseData['humidity_min'] ?? $humidity['min'] ?? null;
        $humidityMax = $phaseData['humidity_max'] ?? $humidity['max'] ?? null;
        $humidityTarget = $phaseData['humidity_target'] ?? $humidity['target'] ?? $this->averageTarget(['min' => $humidityMin, 'max' => $humidityMax]);

        $co2Min = $phaseData['co2_min'] ?? $co2['min'] ?? null;
        $co2Max = $phaseData['co2_max'] ?? $co2['max'] ?? null;
        $co2Target = $phaseData['co2_target'] ?? $co2['target'] ?? $this->averageTarget(['min' => $co2Min, 'max' => $co2Max]);

        $dliMin = $phaseData['dli_min'] ?? $dli['min'] ?? null;
        $dliMax = $phaseData['dli_max'] ?? $dli['max'] ?? null;
        $dliTarget = $phaseData['dli_target'] ?? $dli['target'] ?? $this->averageTarget(['min' => $dliMin, 'max' => $dliMax]);

        $durationDays = $phaseData['duration_days'] ?? null;
        $durationHours = $phaseData['duration_hours'] ?? null;
        if ($durationHours === null && $durationDays !== null) {
            $durationHours = (int) round($durationDays * 24);
        }

        $irrigationMode = $phaseData['irrigation_mode'] ?? $irrigation['mode'] ?? null;
        if ($irrigationMode === null && ! empty($irrigation)) {
            $irrigationMode = 'SUBSTRATE';
        }

        $mistMode = $phaseData['mist_mode'] ?? $mist['mode'] ?? null;
        if ($mistMode === null && ! empty($mist)) {
            $mistMode = 'NORMAL';
        }

        $extensions = $this->buildPhaseExtensions($phaseData);

        return [
            'stage_template_id' => $stageTemplate?->id,
            'phase_index' => $phaseData['phase_index'],
            'name' => $phaseData['name'],
            'ph_target' => $phTarget,
            'ph_min' => $phMin,
            'ph_max' => $phMax,
            'ec_target' => $ecTarget,
            'ec_min' => $ecMin,
            'ec_max' => $ecMax,
            'nutrient_program_code' => $nutritionProfile['program_code'],
            'nutrient_npk_ratio_pct' => $nutritionProfile['npk_ratio_pct'],
            'nutrient_calcium_ratio_pct' => $nutritionProfile['calcium_ratio_pct'],
            'nutrient_micro_ratio_pct' => $nutritionProfile['micro_ratio_pct'],
            'nutrient_npk_dose_ml_l' => $nutritionProfile['npk_dose_ml_l'],
            'nutrient_calcium_dose_ml_l' => $nutritionProfile['calcium_dose_ml_l'],
            'nutrient_micro_dose_ml_l' => $nutritionProfile['micro_dose_ml_l'],
            'nutrient_npk_product_id' => $nutritionProfile['npk_product_id'],
            'nutrient_calcium_product_id' => $nutritionProfile['calcium_product_id'],
            'nutrient_micro_product_id' => $nutritionProfile['micro_product_id'],
            'nutrient_dose_delay_sec' => $nutritionProfile['dose_delay_sec'],
            'nutrient_ec_stop_tolerance' => $nutritionProfile['ec_stop_tolerance'],
            'irrigation_mode' => $irrigationMode,
            'irrigation_interval_sec' => $phaseData['irrigation_interval_sec'] ?? $irrigation['interval_sec'] ?? null,
            'irrigation_duration_sec' => $phaseData['irrigation_duration_sec'] ?? $irrigation['duration_sec'] ?? null,
            'lighting_photoperiod_hours' => $phaseData['lighting_photoperiod_hours'] ?? $lighting['photoperiod_hours'] ?? null,
            'lighting_start_time' => $phaseData['lighting_start_time'] ?? $lighting['start_time'] ?? null,
            'mist_interval_sec' => $phaseData['mist_interval_sec'] ?? $mist['interval_sec'] ?? null,
            'mist_duration_sec' => $phaseData['mist_duration_sec'] ?? $mist['duration_sec'] ?? null,
            'mist_mode' => $mistMode,
            'temp_air_target' => $tempTarget,
            'humidity_target' => $humidityTarget,
            'co2_target' => $co2Target !== null ? (int) round($co2Target) : null,
            'progress_model' => $phaseData['progress_model'] ?? 'TIME',
            'duration_hours' => $durationHours,
            'duration_days' => $durationDays,
            'base_temp_c' => $phaseData['base_temp_c'] ?? null,
            'target_gdd' => $phaseData['target_gdd'] ?? null,
            'dli_target' => $dliTarget,
            'extensions' => $extensions,
        ];
    }

    private function buildNutritionProfile(array $phaseData, ?string $stageCode = null): array
    {
        $nutrition = is_array($phaseData['nutrition'] ?? null) ? $phaseData['nutrition'] : [];
        $components = is_array($nutrition['components'] ?? null) ? $nutrition['components'] : [];
        $defaults = $this->defaultNutritionRatiosByStage($stageCode);
        $defaultDoses = $this->defaultNutritionDosesByStage($stageCode);
        $programCode = $phaseData['nutrient_program_code']
            ?? $nutrition['program_code']
            ?? 'YARAREGA_CALCINIT_HAIFA_MICRO_V1';
        $defaultProducts = $this->defaultNutritionProductsByProgram($programCode);

        $npkRatio = $phaseData['nutrient_npk_ratio_pct']
            ?? data_get($components, 'npk.ratio_pct')
            ?? $defaults['npk'];
        $calciumRatio = $phaseData['nutrient_calcium_ratio_pct']
            ?? data_get($components, 'calcium.ratio_pct')
            ?? $defaults['calcium'];
        $microRatio = $phaseData['nutrient_micro_ratio_pct']
            ?? data_get($components, 'micro.ratio_pct')
            ?? $defaults['micro'];

        $normalized = $this->normalizeNutritionRatios((float) $npkRatio, (float) $calciumRatio, (float) $microRatio);

        return [
            'program_code' => $programCode,
            'npk_ratio_pct' => $normalized['npk'],
            'calcium_ratio_pct' => $normalized['calcium'],
            'micro_ratio_pct' => $normalized['micro'],
            'npk_dose_ml_l' => $phaseData['nutrient_npk_dose_ml_l'] ?? data_get($components, 'npk.dose_ml_per_l') ?? $defaultDoses['npk'],
            'calcium_dose_ml_l' => $phaseData['nutrient_calcium_dose_ml_l'] ?? data_get($components, 'calcium.dose_ml_per_l') ?? $defaultDoses['calcium'],
            'micro_dose_ml_l' => $phaseData['nutrient_micro_dose_ml_l'] ?? data_get($components, 'micro.dose_ml_per_l') ?? $defaultDoses['micro'],
            'npk_product_id' => $phaseData['nutrient_npk_product_id'] ?? data_get($components, 'npk.product_id') ?? $defaultProducts['npk_product_id'],
            'calcium_product_id' => $phaseData['nutrient_calcium_product_id'] ?? data_get($components, 'calcium.product_id') ?? $defaultProducts['calcium_product_id'],
            'micro_product_id' => $phaseData['nutrient_micro_product_id'] ?? data_get($components, 'micro.product_id') ?? $defaultProducts['micro_product_id'],
            'dose_delay_sec' => $phaseData['nutrient_dose_delay_sec'] ?? $nutrition['dose_delay_sec'] ?? 12,
            'ec_stop_tolerance' => $phaseData['nutrient_ec_stop_tolerance'] ?? $nutrition['ec_stop_tolerance'] ?? 0.07,
        ];
    }

    private function seedNutrientProducts(): void
    {
        $terraTarsaMultiMicroPayload = [
            'manufacturer' => 'TerraTarsa',
            'name' => 'Powerfol Oil Crop',
            'component' => 'micro',
            'composition' => 'N 15%, MgO 1%, B 0.5%, Cu 0.04%, Fe 0.14%, Mn 1.1%, Mo 0.09%, Zn 1%',
            'recommended_stage' => 'VEG,FLOWER,FRUIT',
            'notes' => 'Жидкое микроудобрение с комплексом микроэлементов для предотвращения и коррекции дефицитов.',
            'metadata' => [
                'source_url' => 'https://terratarsa.com/en/prd/powerfol-oil-crops-3/',
                'system_code' => 'TERRATARSA_NOVALON_DUCANIT_POWERFOLZN_V1',
            ],
        ];

        // Миграция legacy-данных: заменяем старую одноэлементную позицию TerraTarsa Zn EDTA на multi-micro.
        $legacyTerraTarsaZn = NutrientProduct::query()
            ->where('manufacturer', 'TerraTarsa')
            ->where('name', 'POWERFOL Zn EDTA')
            ->where('component', 'micro')
            ->first();

        if (
            $legacyTerraTarsaZn !== null &&
            ! NutrientProduct::query()
                ->where('manufacturer', $terraTarsaMultiMicroPayload['manufacturer'])
                ->where('name', $terraTarsaMultiMicroPayload['name'])
                ->where('component', $terraTarsaMultiMicroPayload['component'])
                ->exists()
        ) {
            $legacyTerraTarsaZn->update([
                'name' => $terraTarsaMultiMicroPayload['name'],
                'composition' => $terraTarsaMultiMicroPayload['composition'],
                'recommended_stage' => $terraTarsaMultiMicroPayload['recommended_stage'],
                'notes' => $terraTarsaMultiMicroPayload['notes'],
                'metadata' => $terraTarsaMultiMicroPayload['metadata'],
            ]);
        }

        $products = [
            [
                'manufacturer' => 'Masterblend',
                'name' => '5-11-26 Hydroponic Formula',
                'component' => 'npk',
                'composition' => 'NPK 5-11-26 + Mg + S + trace',
                'recommended_stage' => 'ROOTING,VEG,FLOWER,FRUIT',
                'notes' => 'Водорастворимая гидропонная формула; в инструкции используется в паре с Calcium Nitrate.',
                'metadata' => [
                    'source_url' => 'https://www.masterblend.com/5-11-26-hydroponic-formula/',
                    'system_code' => 'MASTERBLEND_51126_CA_HAIFA_MICRO_V1',
                ],
            ],
            [
                'manufacturer' => 'Masterblend',
                'name' => 'Tomato 4-18-38',
                'component' => 'npk',
                'composition' => 'NPK 4-18-38',
                'recommended_stage' => 'ROOTING,VEG,FLOWER,FRUIT',
                'notes' => 'Базовый комплекс NPK для двухкомпонентных гидросхем с отдельным кальцием.',
                'metadata' => [
                    'source_url' => 'https://www.masterblend.com/4-18-38-tomato-formula/',
                    'system_code' => 'MASTERBLEND_41838_CA_HAIFA_MICRO_V1',
                ],
            ],
            [
                'manufacturer' => 'Yara',
                'name' => 'YaraLiva Calcinit',
                'component' => 'calcium',
                'composition' => '15.5-0-0 + 19% Ca',
                'recommended_stage' => 'ROOTING,VEG,FLOWER,FRUIT',
                'notes' => 'Источник нитратного азота и кальция; хранить отдельно от фосфатов/сульфатов.',
                'metadata' => [
                    'source_url' => 'https://www.yara.com/crop-nutrition/our-global-fertilizer-brands/yaraliva/',
                    'system_code' => 'YARAREGA_CALCINIT_HAIFA_MICRO_V1',
                ],
            ],
            [
                'manufacturer' => 'Haifa',
                'name' => 'Micro Hydroponic Mix',
                'component' => 'micro',
                'composition' => 'Fe, Mn, Zn, Cu, B, Mo',
                'recommended_stage' => 'GERMINATION,ROOTING,VEG,FLOWER,FRUIT',
                'notes' => 'Хелатный микс микроэлементов для гидропоники.',
                'metadata' => [
                    'source_url' => 'https://www.haifa-group.com/haifa-micro-hydroponic-mix',
                    'system_code' => 'YARAREGA_CALCINIT_HAIFA_MICRO_V1',
                ],
            ],
            [
                'manufacturer' => 'Yara',
                'name' => 'YaraRega Water-Soluble NPK',
                'component' => 'npk',
                'composition' => 'NPK range (various ratios) + S + optional Mg/Zn/B',
                'recommended_stage' => 'ROOTING,VEG,FLOWER,FRUIT',
                'notes' => 'Линейка водорастворимых NPK для фертигации, включая варианты под разные стадии роста.',
                'metadata' => [
                    'source_url' => 'https://www.yara.com/crop-nutrition/our-global-fertilizer-brands/yararega/',
                    'system_code' => 'YARAREGA_CALCINIT_HAIFA_MICRO_V1',
                ],
            ],
            [
                'manufacturer' => 'Yara',
                'name' => 'YaraTera Kristalon 18-18-18',
                'component' => 'npk',
                'composition' => 'NPK 18-18-18',
                'recommended_stage' => 'VEG',
                'notes' => 'Универсальная комплексная база NPK для вегетативных фаз.',
                'metadata' => [
                    'source_url' => 'https://www.yara.com/crop-nutrition/our-global-fertilizer-brands/yaratera/',
                    'system_code' => 'YARAREGA_CALCINIT_HAIFA_MICRO_V1',
                ],
            ],
            [
                'manufacturer' => 'Буйские удобрения',
                'name' => 'Акварин для томатов, перцев, баклажанов',
                'component' => 'npk',
                'composition' => 'NPK 6-12-36 + MgO + S + микроэлементы',
                'recommended_stage' => 'FLOWER,FRUIT',
                'notes' => 'Водорастворимое NPK-удобрение из схем питания BHZ для томатов, перцев и баклажанов.',
                'metadata' => [
                    'source_url' => 'https://bhzshop.ru/catalog/dlya-sada-i-ogoroda/akvarin-dlya-tomatov/',
                    'system_code' => 'BHZ_AKVARIN_CALCIUM_AKVAMIX_V1',
                ],
            ],
            [
                'manufacturer' => 'Буйские удобрения',
                'name' => 'Селитра кальциевая',
                'component' => 'calcium',
                'composition' => 'N 14.9%, CaO 27%',
                'recommended_stage' => 'ROOTING,VEG,FLOWER,FRUIT',
                'notes' => 'Азотно-кальциевое водорастворимое удобрение для фертигации и корневых подкормок.',
                'metadata' => [
                    'source_url' => 'https://bhzshop.ru/catalog/kompleksnye-udobreniya/selitra-kaltsievaya/',
                    'system_code' => 'BHZ_AKVARIN_CALCIUM_AKVAMIX_V1',
                ],
            ],
            [
                'manufacturer' => 'Буйские удобрения',
                'name' => 'Аквамикс микроэлементный комплекс',
                'component' => 'micro',
                'composition' => 'Fe, Mn, Zn, Cu, Ca, B, Mo (хелатные формы для ряда элементов)',
                'recommended_stage' => 'GERMINATION,ROOTING,VEG,FLOWER,FRUIT',
                'notes' => 'Микроэлементный комплекс для профилактики хлорозов и коррекции микрообеспечения.',
                'metadata' => [
                    'source_url' => 'https://bhzshop.ru/catalog/mikroelementy-garden/akvamiks-mikroelementnyy-kompleks/',
                    'system_code' => 'BHZ_AKVARIN_CALCIUM_AKVAMIX_V1',
                ],
            ],
            [
                'manufacturer' => 'TerraTarsa',
                'name' => 'NovaloN 19-19-19+2MgO+ME',
                'component' => 'npk',
                'composition' => 'NPK 19-19-19 + MgO + хелатные микроэлементы',
                'recommended_stage' => 'VEG',
                'notes' => 'Комплексное водорастворимое удобрение с микроэлементами для активного вегетативного роста.',
                'metadata' => [
                    'source_url' => 'https://terratarsa.com/en/prd/novalon-19-19-192mgome/',
                    'system_code' => 'TERRATARSA_NOVALON_DUCANIT_POWERFOLZN_V1',
                ],
            ],
            [
                'manufacturer' => 'TerraTarsa',
                'name' => 'DUCANIT calcium nitrate',
                'component' => 'calcium',
                'composition' => 'Азотно-кальциевое полностью растворимое удобрение (кальциевая селитра)',
                'recommended_stage' => 'ROOTING,VEG,FLOWER,FRUIT',
                'notes' => 'Компонент кальциевой линии в системах фертигации овощных и плодово-ягодных культур.',
                'metadata' => [
                    'source_url' => 'https://terratarsa.com/en/special-nitrogen-calcium-fertilizer/',
                    'system_code' => 'TERRATARSA_NOVALON_DUCANIT_POWERFOLZN_V1',
                ],
            ],
            [
                'manufacturer' => 'TerraTarsa',
                'name' => 'Powerfol Oil Crop',
                'component' => 'micro',
                'composition' => 'N 15%, MgO 1%, B 0.5%, Cu 0.04%, Fe 0.14%, Mn 1.1%, Mo 0.09%, Zn 1%',
                'recommended_stage' => 'VEG,FLOWER,FRUIT',
                'notes' => 'Жидкое микроудобрение с комплексом микроэлементов для предотвращения и коррекции дефицитов.',
                'metadata' => [
                    'source_url' => 'https://terratarsa.com/en/prd/powerfol-oil-crops-3/',
                    'system_code' => 'TERRATARSA_NOVALON_DUCANIT_POWERFOLZN_V1',
                ],
            ],
            [
                'manufacturer' => 'АгроМастер',
                'name' => 'АгроМастер 20-20-20 + микро',
                'component' => 'npk',
                'composition' => 'NPK 20-20-20 + микроэлементы',
                'recommended_stage' => 'ROOTING,VEG',
                'notes' => 'Формула для рассады и ранних этапов роста в стандартных питательных растворах.',
                'metadata' => [
                    'source_url' => 'https://agromaster.ru/ststandartpitatrastv',
                    'system_code' => 'AGROMASTER_202020_CANO3_BOROPLUS_V1',
                ],
            ],
            [
                'manufacturer' => 'АгроМастер',
                'name' => 'Нитрат кальция (кальциевая селитра)',
                'component' => 'calcium',
                'composition' => 'N 12%, CaO 24%',
                'recommended_stage' => 'ROOTING,VEG,FLOWER,FRUIT',
                'notes' => 'Кальциевая селитра (четырёхводная, кристаллическая), водорастворимая для фертигации.',
                'metadata' => [
                    'source_url' => 'https://agromaster.ru/prostminudobreniya',
                    'system_code' => 'AGROMASTER_202020_CANO3_BOROPLUS_V1',
                ],
            ],
            [
                'manufacturer' => 'АгроМастер',
                'name' => 'Бороплюс',
                'component' => 'micro',
                'composition' => 'Органическая форма бора (микроудобрение)',
                'recommended_stage' => 'FLOWER,FRUIT',
                'notes' => 'Микроудобрение для профилактики дефицита бора при листовых и капельных подкормках.',
                'metadata' => [
                    'source_url' => 'https://agromaster.ru/boroplus',
                    'system_code' => 'AGROMASTER_202020_CANO3_BOROPLUS_V1',
                ],
            ],
        ];

        foreach ($products as $payload) {
            $product = NutrientProduct::query()->firstOrCreate(
                [
                    'manufacturer' => $payload['manufacturer'],
                    'name' => $payload['name'],
                    'component' => $payload['component'],
                ],
                $payload
            );
            $this->nutrientProductIds[$payload['manufacturer'].'|'.$payload['name'].'|'.$payload['component']] = $product->id;
        }
    }

    private function defaultNutritionProductsByProgram(string $programCode): array
    {
        $code = strtoupper($programCode);
        $masterblend = [
            'npk_product_id' => $this->nutrientProductIds['Masterblend|5-11-26 Hydroponic Formula|npk']
                ?? $this->nutrientProductIds['Masterblend|Tomato 4-18-38|npk']
                ?? null,
            'calcium_product_id' => $this->nutrientProductIds['Yara|YaraLiva Calcinit|calcium'] ?? null,
            'micro_product_id' => $this->nutrientProductIds['Haifa|Micro Hydroponic Mix|micro'] ?? null,
        ];
        $yaraRega = [
            'npk_product_id' => $this->nutrientProductIds['Yara|YaraRega Water-Soluble NPK|npk']
                ?? $this->nutrientProductIds['Yara|YaraTera Kristalon 18-18-18|npk']
                ?? $masterblend['npk_product_id'],
            'calcium_product_id' => $this->nutrientProductIds['Yara|YaraLiva Calcinit|calcium'] ?? $masterblend['calcium_product_id'],
            'micro_product_id' => $this->nutrientProductIds['Haifa|Micro Hydroponic Mix|micro'] ?? $masterblend['micro_product_id'],
        ];
        $bhz = [
            'npk_product_id' => $this->nutrientProductIds['Буйские удобрения|Акварин для томатов, перцев, баклажанов|npk']
                ?? $yaraRega['npk_product_id'],
            'calcium_product_id' => $this->nutrientProductIds['Буйские удобрения|Селитра кальциевая|calcium']
                ?? $yaraRega['calcium_product_id'],
            'micro_product_id' => $this->nutrientProductIds['Буйские удобрения|Аквамикс микроэлементный комплекс|micro']
                ?? $yaraRega['micro_product_id'],
        ];
        $terraTarsa = [
            'npk_product_id' => $this->nutrientProductIds['TerraTarsa|NovaloN 19-19-19+2MgO+ME|npk']
                ?? $yaraRega['npk_product_id'],
            'calcium_product_id' => $this->nutrientProductIds['TerraTarsa|DUCANIT calcium nitrate|calcium']
                ?? $yaraRega['calcium_product_id'],
            'micro_product_id' => $this->nutrientProductIds['TerraTarsa|Powerfol Oil Crop|micro']
                ?? $yaraRega['micro_product_id'],
        ];
        $agromaster = [
            'npk_product_id' => $this->nutrientProductIds['АгроМастер|АгроМастер 20-20-20 + микро|npk']
                ?? $yaraRega['npk_product_id'],
            'calcium_product_id' => $this->nutrientProductIds['АгроМастер|Нитрат кальция (кальциевая селитра)|calcium']
                ?? $yaraRega['calcium_product_id'],
            'micro_product_id' => $this->nutrientProductIds['АгроМастер|Бороплюс|micro']
                ?? $yaraRega['micro_product_id'],
        ];

        return match ($code) {
            'MASTERBLEND_51126_CA_HAIFA_MICRO_V1',
            'MASTERBLEND_41838_CA_HAIFA_MICRO_V1',
            'MASTERBLEND_3PART_V1',
            'GENERIC_3PART_V1' => $masterblend,
            'YARAREGA_CALCINIT_HAIFA_MICRO_V1' => $yaraRega,
            'BHZ_AKVARIN_CALCIUM_AKVAMIX_V1' => $bhz,
            'TERRATARSA_NOVALON_DUCANIT_POWERFOLZN_V1' => $terraTarsa,
            'AGROMASTER_202020_CANO3_BOROPLUS_V1' => $agromaster,
            default => $yaraRega,
        };
    }

    private function defaultNutritionRatiosByStage(?string $stageCode): array
    {
        $code = strtoupper((string) $stageCode);

        return match ($code) {
            'GERMINATION' => ['npk' => 45.0, 'calcium' => 45.0, 'micro' => 10.0],
            'ROOTING' => ['npk' => 45.0, 'calcium' => 45.0, 'micro' => 10.0],
            'VEG' => ['npk' => 46.0, 'calcium' => 44.0, 'micro' => 10.0],
            'FLOWER' => ['npk' => 43.0, 'calcium' => 44.0, 'micro' => 13.0],
            'FRUIT' => ['npk' => 41.0, 'calcium' => 44.0, 'micro' => 15.0],
            'HARVEST' => ['npk' => 40.0, 'calcium' => 45.0, 'micro' => 15.0],
            default => ['npk' => 44.0, 'calcium' => 44.0, 'micro' => 12.0],
        };
    }

    private function defaultNutritionDosesByStage(?string $stageCode): array
    {
        $code = strtoupper((string) $stageCode);

        return match ($code) {
            'GERMINATION' => ['npk' => 0.30, 'calcium' => 0.30, 'micro' => 0.05],
            'ROOTING' => ['npk' => 0.45, 'calcium' => 0.45, 'micro' => 0.07],
            'VEG' => ['npk' => 0.60, 'calcium' => 0.60, 'micro' => 0.10],
            'FLOWER' => ['npk' => 0.70, 'calcium' => 0.65, 'micro' => 0.12],
            'FRUIT' => ['npk' => 0.75, 'calcium' => 0.70, 'micro' => 0.15],
            'HARVEST' => ['npk' => 0.40, 'calcium' => 0.40, 'micro' => 0.06],
            default => ['npk' => 0.55, 'calcium' => 0.55, 'micro' => 0.09],
        };
    }

    private function normalizeNutritionRatios(float $npk, float $calcium, float $micro): array
    {
        $npk = max(0.0, $npk);
        $calcium = max(0.0, $calcium);
        $micro = max(0.0, $micro);

        $sum = $npk + $calcium + $micro;
        if ($sum <= 0.0) {
            return ['npk' => 45.0, 'calcium' => 35.0, 'micro' => 20.0];
        }

        return [
            'npk' => round(($npk / $sum) * 100.0, 2),
            'calcium' => round(($calcium / $sum) * 100.0, 2),
            'micro' => round(($micro / $sum) * 100.0, 2),
        ];
    }

    private function buildPhaseExtensions(array $phaseData): ?array
    {
        $extensions = $phaseData['extensions'] ?? [];

        if (! empty($phaseData['agronomy'])) {
            $extensions['agronomy'] = $phaseData['agronomy'];
        }

        foreach (['temp_air' => 'temp_air', 'humidity' => 'humidity', 'co2' => 'co2', 'dli' => 'dli'] as $key => $prefix) {
            $range = $phaseData[$key] ?? null;
            if (! is_array($range)) {
                continue;
            }
            if (array_key_exists('min', $range)) {
                $extensions[$prefix.'_min'] = $range['min'];
            }
            if (array_key_exists('max', $range)) {
                $extensions[$prefix.'_max'] = $range['max'];
            }
        }

        $lighting = $phaseData['lighting'] ?? null;
        if (is_array($lighting)) {
            $lightingMeta = array_intersect_key($lighting, array_flip(['ppfd', 'ppfd_max', 'spectrum', 'dimming_percent']));
            if (! empty($lightingMeta)) {
                $extensions['lighting'] = $lightingMeta;
            }
        }

        $irrigation = $phaseData['irrigation'] ?? null;
        if (is_array($irrigation)) {
            $irrigationMeta = array_intersect_key(
                $irrigation,
                array_flip(['drain_target_percent', 'drain_ec_target', 'drain_ph_target', 'pulse_count_per_day', 'start_time', 'end_time'])
            );
            if (! empty($irrigationMeta)) {
                $extensions['irrigation'] = $irrigationMeta;
            }
        }

        if (! empty($phaseData['vpd_target_kpa'])) {
            $extensions['vpd_target_kpa'] = $phaseData['vpd_target_kpa'];
        }

        return empty($extensions) ? null : $extensions;
    }

    private function seedGrowCycles(Collection $revisions): void
    {
        $zones = Zone::all();
        if ($zones->isEmpty()) {
            $this->command->warn('Зоны не найдены. Запустите ExtendedGreenhousesZonesSeeder сначала.');

            return;
        }

        $plants = Plant::all();
        if ($plants->isEmpty()) {
            $this->command->warn('Растения не найдены. Запустите PlantTaxonomySeeder сначала.');

            return;
        }

        if ($revisions->isEmpty()) {
            $this->command->warn('Ревизии рецептов не найдены.');

            return;
        }

        $revisionPool = $revisions->filter(function (RecipeRevision $revision) {
            return $revision->recipe && $revision->recipe->plants->isNotEmpty();
        });

        if ($revisionPool->isEmpty()) {
            $this->command->warn('Ревизии рецептов без привязанных растений.');

            return;
        }

        $growCycleService = app(GrowCycleService::class);
        $userId = User::where('role', 'admin')->value('id') ?? User::value('id');
        $zonesByStatus = $zones->groupBy('status');
        $pausedZoneIds = $zonesByStatus->get('PAUSED', collect())->pluck('id')->all();
        $stoppedZones = $zonesByStatus->get('STOPPED', collect());
        $plannedZoneId = $stoppedZones->first()?->id;
        $skipZoneId = $stoppedZones->skip(1)->first()?->id;

        if (! $plannedZoneId && $zones->isNotEmpty()) {
            $plannedZoneId = $zones->first()->id;
        }
        if (! $skipZoneId && $zones->count() > 1) {
            $skipZoneId = $zones->firstWhere('id', '!=', $plannedZoneId)?->id;
        }

        $plannedZoneIds = $plannedZoneId ? [$plannedZoneId] : [];
        $skipZoneIds = $skipZoneId ? [$skipZoneId] : [];

        foreach ($zones as $zone) {
            if (in_array($zone->id, $skipZoneIds, true)) {
                continue;
            }
            if ($zone->activeGrowCycle) {
                continue;
            }

            /** @var RecipeRevision $revision */
            $revision = $revisionPool->random();
            $plantsForRecipe = $revision->recipe->plants;
            $plant = $plantsForRecipe->firstWhere('pivot.is_default', true) ?? $plantsForRecipe->first();

            if (! $plant) {
                continue;
            }

            $plannedCycle = in_array($zone->id, $plannedZoneIds, true);
            $startedAt = $plannedCycle
                ? now()->addDays(rand(2, 7))
                : now()->subDays(rand(1, 30));
            $zoneStatus = strtolower((string) $zone->status);
            $startImmediately = ! $plannedCycle && ! in_array($zoneStatus, ['offline', 'critical'], true);

            try {
                $cycle = $growCycleService->createCycle(
                    $zone,
                    $revision,
                    $plant->id,
                    [
                        'planting_at' => $startedAt->format('Y-m-d H:i:s'),
                        'start_immediately' => $startImmediately,
                        'batch_label' => 'BATCH-'.Str::upper(Str::random(6)),
                        'notes' => "Цикл выращивания для зоны {$zone->name}",
                    ],
                    $userId
                );

                if ($cycle->status === \App\Enums\GrowCycleStatus::RUNNING) {
                    $growCycleService->computeExpectedHarvest($cycle);
                }

                if (in_array($zone->id, $pausedZoneIds, true) && $cycle->status === \App\Enums\GrowCycleStatus::RUNNING) {
                    $growCycleService->pause($cycle, $userId);
                }
            } catch (\Throwable $e) {
                $this->command->warn("Не удалось создать цикл для зоны {$zone->id}: {$e->getMessage()}");
            }
        }
    }

    private function resolveStageTemplate(Recipe $recipe, array $phaseData, Collection $templates): ?GrowStageTemplate
    {
        $stageCode = strtoupper((string) ($phaseData['stage_code'] ?? ''));
        if ($stageCode !== '') {
            return $templates->firstWhere('code', $stageCode) ?? $templates->first();
        }

        $phaseName = Str::lower($phaseData['name'] ?? '');
        $recipeName = Str::lower($recipe->name);

        if (str_contains($phaseName, 'проращ') || str_contains($phaseName, 'germin')) {
            return $templates->firstWhere('code', 'GERMINATION') ?? $templates->first();
        }

        if (str_contains($phaseName, 'рассад') || str_contains($phaseName, 'посад')) {
            return $templates->firstWhere('code', 'PLANTING') ?? $templates->first();
        }

        if (str_contains($phaseName, 'вегет') || str_contains($phaseName, 'рост')) {
            return $templates->firstWhere('code', 'VEG') ?? $templates->first();
        }

        if (str_contains($phaseName, 'цвет')) {
            return $templates->firstWhere('code', 'FLOWER') ?? $templates->first();
        }

        if (str_contains($phaseName, 'плод') || str_contains($phaseName, 'созрев')) {
            return $templates->firstWhere('code', 'FRUIT') ?? $templates->first();
        }

        if (str_contains($phaseName, 'сбор') || str_contains($phaseName, 'harvest')) {
            return $templates->firstWhere('code', 'HARVEST') ?? $templates->first();
        }

        if (str_contains($recipeName, 'салат') || str_contains($recipeName, 'lettuce')) {
            return match ($phaseData['phase_index']) {
                0 => $templates->firstWhere('code', 'GERMINATION'),
                1 => $templates->firstWhere('code', 'VEG'),
                default => $templates->firstWhere('code', 'HARVEST'),
            } ?? $templates->first();
        }

        if (str_contains($recipeName, 'томат') || str_contains($recipeName, 'tomato')) {
            return match ($phaseData['phase_index']) {
                0 => $templates->firstWhere('code', 'PLANTING'),
                1 => $templates->firstWhere('code', 'VEG'),
                default => $templates->firstWhere('code', 'FRUIT'),
            } ?? $templates->first();
        }

        $fallbackCode = match ($phaseData['phase_index']) {
            0 => 'GERMINATION',
            1 => 'VEG',
            2 => 'FLOWER',
            3 => 'FRUIT',
            default => 'VEG',
        };

        return $templates->firstWhere('code', $fallbackCode) ?? $templates->first();
    }

    private function averageTarget(array $target): ?float
    {
        $min = $target['min'] ?? null;
        $max = $target['max'] ?? null;

        if ($min === null && $max === null) {
            return null;
        }

        if ($min === null) {
            return (float) $max;
        }

        if ($max === null) {
            return (float) $min;
        }

        return round(((float) $min + (float) $max) / 2, 2);
    }
}
