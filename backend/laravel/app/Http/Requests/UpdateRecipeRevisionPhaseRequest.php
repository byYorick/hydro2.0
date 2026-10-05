<?php

namespace App\Http\Requests;

use App\Support\Recipes\RecipePhaseRules;
use Illuminate\Foundation\Http\FormRequest;

class UpdateRecipeRevisionPhaseRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    /**
     * @return array<string, mixed>
     */
    public function rules(): array
    {
        return RecipePhaseRules::update();
    }
}
