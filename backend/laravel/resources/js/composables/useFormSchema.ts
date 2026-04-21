import { computed, reactive, shallowRef, watch, type ComputedRef } from 'vue';
import type { ZodType } from 'zod';

export type FieldErrors = Record<string, string>;

export type ParseResult<T> =
    | { success: true; data: T }
    | { success: false; issues: Array<{ path: string; message: string }> };

export interface UseFormSchemaResult<T extends Record<string, unknown>> {
    state: T;
    errors: ComputedRef<FieldErrors>;
    isValid: ComputedRef<boolean>;
    parsed: ComputedRef<ParseResult<T>>;
    setField: <K extends keyof T>(key: K, value: T[K]) => void;
    reset: (next?: Partial<T>) => void;
    validate: () => FieldErrors;
    toPayload: () => T | null;
}

type Issue = { path: ReadonlyArray<PropertyKey>; message: string };

function issuesToErrors(issues: ReadonlyArray<Issue>): FieldErrors {
    const out: FieldErrors = {};
    for (const issue of issues) {
        const path = issue.path.map(String).join('.');
        if (!(path in out)) {
            out[path] = issue.message;
        }
    }
    return out;
}

export function useFormSchema<T extends Record<string, unknown>>(
    schema: ZodType<T>,
    initial: Partial<T> = {},
): UseFormSchemaResult<T> {
    const state = reactive({ ...(initial as T) }) as T;
    const errorsStore = reactive<FieldErrors>({});
    const parsedRef = shallowRef<ParseResult<T>>({ success: false, issues: [] });

    const runValidation = (): FieldErrors => {
        const result = schema.safeParse(state);
        if (result.success) {
            parsedRef.value = { success: true, data: result.data as T };
            for (const key of Object.keys(errorsStore)) {
                delete errorsStore[key];
            }
        } else {
            const issues = (result.error?.issues ?? []) as Issue[];
            const normalised = issues.map((issue) => ({
                path: issue.path.map(String).join('.'),
                message: issue.message,
            }));
            parsedRef.value = { success: false, issues: normalised };
            for (const key of Object.keys(errorsStore)) {
                delete errorsStore[key];
            }
            Object.assign(errorsStore, issuesToErrors(issues));
        }
        return { ...errorsStore };
    };

    watch(() => ({ ...state }), runValidation, { deep: true, immediate: true });

    const errors = computed<FieldErrors>(() => ({ ...errorsStore }));
    const isValid = computed<boolean>(() => Object.keys(errorsStore).length === 0);
    const parsed = computed<ParseResult<T>>(() => parsedRef.value);

    return {
        state,
        errors,
        isValid,
        parsed,
        setField: <K extends keyof T>(key: K, value: T[K]) => {
            (state as T)[key] = value;
        },
        reset: (next?: Partial<T>) => {
            for (const key of Object.keys(state) as (keyof T)[]) {
                delete (state as Record<string, unknown>)[key as string];
            }
            Object.assign(state, initial, next ?? {});
        },
        validate: runValidation,
        toPayload: () => {
            const snapshot = parsedRef.value;
            return snapshot.success ? snapshot.data : null;
        },
    };
}
