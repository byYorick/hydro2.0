<?php

namespace Tests\Unit;

use App\Models\GrowStageTemplate;
use App\Models\RecipeRevisionPhase;
use Tests\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

class GrowStageTemplateTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function it_has_phases_relationship()
    {
        $template = GrowStageTemplate::factory()->create();
        $phase = RecipeRevisionPhase::factory()->create([
            'stage_template_id' => $template->id,
        ]);

        $this->assertTrue($template->phases->contains($phase));
    }

    #[Test]
    public function it_casts_ui_meta_to_array()
    {
        $template = GrowStageTemplate::factory()->create([
            'ui_meta' => ['color' => '#ff0000', 'icon' => '🌱'],
        ]);

        $this->assertIsArray($template->ui_meta);
        $this->assertEquals('#ff0000', $template->ui_meta['color']);
    }
}
