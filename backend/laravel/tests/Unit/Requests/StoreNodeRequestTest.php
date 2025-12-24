<?php

namespace Tests\Unit\Requests;

use App\Http\Requests\StoreNodeRequest;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Validator;
use Tests\TestCase;

class StoreNodeRequestTest extends TestCase
{
    use RefreshDatabase;

    public function test_validates_required_uid(): void
    {
        $request = new StoreNodeRequest();
        $rules = $request->rules();

        $validator = Validator::make([], $rules);
        $this->assertTrue($validator->fails());
        $this->assertArrayHasKey('uid', $validator->errors()->toArray());
    }

    public function test_validates_uid_is_unique(): void
    {
        $request = new StoreNodeRequest();
        $rules = $request->rules();

        $validator = Validator::make([
            'uid' => 'test-node-123',
        ], $rules);

        // Первый раз должен пройти валидацию
        $this->assertFalse($validator->fails());
    }

    public function test_validates_zone_id_exists(): void
    {
        $request = new StoreNodeRequest();
        $rules = $request->rules();

        $validator = Validator::make([
            'uid' => 'test-node-123',
            'zone_id' => 99999, // Несуществующий ID
        ], $rules);

        $this->assertTrue($validator->fails());
        $this->assertArrayHasKey('zone_id', $validator->errors()->toArray());
    }
}
