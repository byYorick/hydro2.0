<?php

namespace App\Http\Controllers;

use App\Models\Greenhouse;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class GreenhouseController extends Controller
{
    public function index(Request $request)
    {
        $items = Greenhouse::query()->latest('id')->paginate(25);
        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function store(Request $request)
    {
        $data = $request->validate([
            'uid' => ['required', 'string', 'max:64', 'unique:greenhouses,uid'],
            'name' => ['required', 'string', 'max:255'],
            'timezone' => ['nullable', 'string', 'max:128'],
            'type' => ['nullable', 'string', 'max:64'],
            'coordinates' => ['nullable', 'array'],
            'description' => ['nullable', 'string'],
        ]);
        $greenhouse = Greenhouse::create($data);
        return response()->json(['status' => 'ok', 'data' => $greenhouse], Response::HTTP_CREATED);
    }

    public function show(Greenhouse $greenhouse)
    {
        $greenhouse->load('zones');
        return response()->json(['status' => 'ok', 'data' => $greenhouse]);
    }

    public function update(Request $request, Greenhouse $greenhouse)
    {
        $data = $request->validate([
            'uid' => ['sometimes', 'string', 'max:64', 'unique:greenhouses,uid,'.$greenhouse->id],
            'name' => ['sometimes', 'string', 'max:255'],
            'timezone' => ['nullable', 'string', 'max:128'],
            'type' => ['nullable', 'string', 'max:64'],
            'coordinates' => ['nullable', 'array'],
            'description' => ['nullable', 'string'],
        ]);
        $greenhouse->update($data);
        return response()->json(['status' => 'ok', 'data' => $greenhouse]);
    }

    public function destroy(Greenhouse $greenhouse)
    {
        $greenhouse->delete();
        return response()->json(['status' => 'ok']);
    }
}


