<?php

use App\Enums\NodeLifecycleState;
use App\Models\DeviceNode;
use App\Services\NodeLifecycleService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

uses(TestCase::class, RefreshDatabase::class);

beforeEach(function () {
    $this->service = app(NodeLifecycleService::class);
});

it('transitions node to active state and sets status online', function () {
    $node = DeviceNode::factory()->create([
        'uid' => 'nd-test-assign',
        'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
        'status' => 'offline',
    ]);

    $result = $this->service->transitionToActive($node, 'commissioned');

    expect($result)->toBeTrue();

    $node->refresh();

    expect($node->lifecycle_state)->toBe(NodeLifecycleState::ACTIVE)
        ->and($node->status)->toBe('online');
});

it('prevents invalid transitions and keeps state unchanged', function () {
    $node = DeviceNode::factory()->create([
        'uid' => 'nd-test-invalid',
        'lifecycle_state' => NodeLifecycleState::MANUFACTURED,
        'status' => 'offline',
    ]);

    $result = $this->service->transitionToActive($node);

    expect($result)->toBeFalse();

    $node->refresh();

    expect($node->lifecycle_state)->toBe(NodeLifecycleState::MANUFACTURED)
        ->and($node->status)->toBe('offline');
});

it('sets node offline when transitioning to maintenance', function () {
    $node = DeviceNode::factory()->create([
        'uid' => 'nd-test-maint',
        'lifecycle_state' => NodeLifecycleState::ACTIVE,
        'status' => 'online',
    ]);

    $result = $this->service->transitionToMaintenance($node, 'manual-check');

    expect($result)->toBeTrue();

    $node->refresh();

    expect($node->lifecycle_state)->toBe(NodeLifecycleState::MAINTENANCE)
        ->and($node->status)->toBe('offline');
});
