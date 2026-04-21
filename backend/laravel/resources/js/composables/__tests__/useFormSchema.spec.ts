import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { nextTick } from 'vue';
import { useFormSchema } from '../useFormSchema';

const schema = z
    .object({
        name: z.string().min(3),
        age: z.number().int().min(0).max(150),
        nested: z.object({ ok: z.boolean() }).optional(),
    })
    .strict();

type Shape = z.infer<typeof schema>;

describe('useFormSchema', () => {
    it('is initially invalid with empty state', async () => {
        const { isValid, errors } = useFormSchema<Shape>(schema);
        await nextTick();
        expect(isValid.value).toBe(false);
        expect(Object.keys(errors.value).length).toBeGreaterThan(0);
    });

    it('becomes valid once all fields satisfy schema', async () => {
        const form = useFormSchema<Shape>(schema, { name: 'abc', age: 10 });
        await nextTick();
        expect(form.isValid.value).toBe(true);
    });

    it('reports per-field error paths', async () => {
        const form = useFormSchema<Shape>(schema, { name: 'a', age: 999 });
        await nextTick();
        expect(form.errors.value).toHaveProperty('name');
        expect(form.errors.value).toHaveProperty('age');
    });

    it('setField triggers re-validation', async () => {
        const form = useFormSchema<Shape>(schema, { name: 'ab', age: 5 });
        await nextTick();
        expect(form.isValid.value).toBe(false);
        form.setField('name', 'valid-name');
        await nextTick();
        expect(form.isValid.value).toBe(true);
    });

    it('reset restores to initial', async () => {
        const form = useFormSchema<Shape>(schema, { name: 'abc', age: 10 });
        await nextTick();
        form.setField('age', -9);
        await nextTick();
        expect(form.isValid.value).toBe(false);
        form.reset();
        await nextTick();
        expect(form.state.age).toBe(10);
    });

    it('toPayload returns typed payload on success', async () => {
        const form = useFormSchema<Shape>(schema, { name: 'abc', age: 10 });
        await nextTick();
        const payload = form.toPayload();
        expect(payload).toEqual({ name: 'abc', age: 10 });
    });

    it('toPayload returns null while invalid', async () => {
        const form = useFormSchema<Shape>(schema, { name: 'a', age: 1 });
        await nextTick();
        expect(form.toPayload()).toBeNull();
    });

    it('reactively updates parsed snapshot', async () => {
        const form = useFormSchema<Shape>(schema, { name: 'abc', age: 10 });
        await nextTick();
        expect(form.parsed.value.success).toBe(true);
        form.setField('age', -1);
        await nextTick();
        expect(form.parsed.value.success).toBe(false);
    });
});
