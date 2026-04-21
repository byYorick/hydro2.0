import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import DiffPreview from '../DiffPreview.vue';

function render(current: Record<string, unknown>, next: Record<string, unknown>) {
    return mount(DiffPreview, { props: { current, next } });
}

describe('DiffPreview', () => {
    it('shows empty state when no changes', () => {
        const wrapper = render({ a: 1 }, { a: 1 });
        expect(wrapper.text()).toContain('Overrides не заданы');
    });

    it('renders replace operation', () => {
        const wrapper = render({ a: 1 }, { a: 2 });
        const rows = wrapper.findAll('tbody tr');
        expect(rows).toHaveLength(1);
        expect(rows[0].classes()).toContain('diff-preview__row--replace');
    });

    it('renders add operation', () => {
        const wrapper = render({}, { b: 'new' });
        const rows = wrapper.findAll('tbody tr');
        expect(rows[0].classes()).toContain('diff-preview__row--add');
        expect(rows[0].text()).toContain('new');
    });

    it('renders remove operation', () => {
        const wrapper = render({ b: 'old' }, {});
        const rows = wrapper.findAll('tbody tr');
        expect(rows[0].classes()).toContain('diff-preview__row--remove');
        expect(rows[0].text()).toContain('old');
    });

    it('strips undefined values from inputs', () => {
        const wrapper = render({ a: 1, b: undefined }, { a: 1 });
        expect(wrapper.text()).toContain('Overrides не заданы');
    });

    it('diffs deeply nested overrides', () => {
        const wrapper = render(
            { irrigation: { mode: 'TIME', interval_sec: 300 } },
            { irrigation: { mode: 'TIME', interval_sec: 600 } },
        );
        const rows = wrapper.findAll('tbody tr');
        expect(rows).toHaveLength(1);
        expect(rows[0].text()).toContain('/irrigation/interval_sec');
        expect(rows[0].text()).toContain('300');
        expect(rows[0].text()).toContain('600');
    });

    it('handles added nested keys', () => {
        const wrapper = render({ overrides: {} }, { overrides: { irrigation: { mode: 'TIME' } } });
        expect(wrapper.findAll('tbody tr').length).toBeGreaterThan(0);
    });

    it('shows object values as JSON string', () => {
        const wrapper = render({}, { overrides: { climate: { day_air_temp_c: 25 } } });
        expect(wrapper.text()).toContain('day_air_temp_c');
    });
});
