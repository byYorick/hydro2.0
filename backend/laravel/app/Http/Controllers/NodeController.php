<?php

namespace App\Http\Controllers;

use App\Models\DeviceNode;
use App\Services\NodeService;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class NodeController extends Controller
{
    public function __construct(
        private NodeService $nodeService
    ) {
    }

    public function index(Request $request)
    {
        $query = DeviceNode::query()->with('zone');
        if ($request->filled('zone_id')) {
            $query->where('zone_id', $request->integer('zone_id'));
        }
        if ($request->filled('status')) {
            $query->where('status', $request->string('status'));
        }
        $items = $query->latest('id')->paginate(25);
        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function store(Request $request)
    {
        $data = $request->validate([
            'zone_id' => ['nullable', 'integer', 'exists:zones,id'],
            'uid' => ['required', 'string', 'max:64', 'unique:nodes,uid'],
            'name' => ['nullable', 'string', 'max:255'],
            'type' => ['nullable', 'string', 'max:64'],
            'fw_version' => ['nullable', 'string', 'max:64'],
            'status' => ['nullable', 'string', 'max:32'],
            'config' => ['nullable', 'array'],
        ]);
        $node = $this->nodeService->create($data);
        return response()->json(['status' => 'ok', 'data' => $node], Response::HTTP_CREATED);
    }

    public function show(DeviceNode $node)
    {
        $node->load('channels');
        return response()->json(['status' => 'ok', 'data' => $node]);
    }

    public function update(Request $request, DeviceNode $node)
    {
        $data = $request->validate([
            'zone_id' => ['nullable', 'integer', 'exists:zones,id'],
            'uid' => ['sometimes', 'string', 'max:64', 'unique:nodes,uid,'.$node->id],
            'name' => ['nullable', 'string', 'max:255'],
            'type' => ['nullable', 'string', 'max:64'],
            'fw_version' => ['nullable', 'string', 'max:64'],
            'status' => ['nullable', 'string', 'max:32'],
            'config' => ['nullable', 'array'],
        ]);
        $node = $this->nodeService->update($node, $data);
        return response()->json(['status' => 'ok', 'data' => $node]);
    }

    public function destroy(DeviceNode $node)
    {
        try {
            $this->nodeService->delete($node);
            return response()->json(['status' => 'ok']);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }
}


