<?php

namespace App\Http\Controllers;

use App\Models\User;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\Hash;
use Illuminate\Validation\Rule;

class UserController extends Controller
{
    public function index(Request $request)
    {
        $query = User::query();
        if ($request->filled('role')) {
            $query->where('role', $request->string('role'));
        }
        if ($request->filled('search')) {
            $search = $request->string('search');
            $query->where(function ($q) use ($search) {
                $q->where('name', 'ilike', "%{$search}%")
                  ->orWhere('email', 'ilike', "%{$search}%");
            });
        }
        $items = $query->select(['id', 'name', 'email', 'role', 'created_at'])
            ->latest('id')
            ->paginate(25);
        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function store(Request $request)
    {
        $data = $request->validate([
            'name' => ['required', 'string', 'max:255'],
            'email' => ['required', 'email', 'max:255', 'unique:users,email'],
            'password' => ['required', 'string', 'min:8'],
            'role' => ['nullable', 'string', Rule::in(['admin', 'operator', 'viewer'])],
        ]);
        $data['password'] = Hash::make($data['password']);
        $data['role'] = $data['role'] ?? 'operator';
        $user = User::create($data);
        return response()->json([
            'status' => 'ok',
            'data' => $user->makeHidden(['password']),
        ], Response::HTTP_CREATED);
    }

    public function show(User $user)
    {
        return response()->json([
            'status' => 'ok',
            'data' => $user->makeHidden(['password', 'remember_token']),
        ]);
    }

    public function update(Request $request, User $user)
    {
        $data = $request->validate([
            'name' => ['sometimes', 'string', 'max:255'],
            'email' => ['sometimes', 'email', 'max:255', Rule::unique('users', 'email')->ignore($user->id)],
            'password' => ['sometimes', 'string', 'min:8'],
            'role' => ['sometimes', 'string', Rule::in(['admin', 'operator', 'viewer'])],
        ]);
        if (isset($data['password'])) {
            $data['password'] = Hash::make($data['password']);
        }
        $user->update($data);
        return response()->json([
            'status' => 'ok',
            'data' => $user->makeHidden(['password', 'remember_token']),
        ]);
    }

    public function destroy(User $user)
    {
        // Prevent deleting yourself
        if ($user->id === auth()->id()) {
            return response()->json([
                'status' => 'error',
                'message' => 'Cannot delete your own account',
            ], Response::HTTP_BAD_REQUEST);
        }
        $user->delete();
        return response()->json(['status' => 'ok']);
    }
}

