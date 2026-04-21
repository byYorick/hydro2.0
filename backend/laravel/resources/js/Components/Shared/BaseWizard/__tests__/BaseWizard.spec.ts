import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import BaseWizard from '../BaseWizard.vue';
import type { WizardStep } from '../types';

const steps: WizardStep[] = [
    { id: 'a', title: 'Шаг A' },
    { id: 'b', title: 'Шаг B' },
    { id: 'c', title: 'Шаг C' },
];

function renderWizard(overrides: Record<string, unknown> = {}) {
    return mount(BaseWizard, {
        props: {
            steps,
            modelValue: 'a',
            ...overrides,
        },
        slots: {
            'step-a': '<div data-test="body-a">A</div>',
            'step-b': '<div data-test="body-b">B</div>',
            'step-c': '<div data-test="body-c">C</div>',
        },
    });
}

describe('BaseWizard', () => {
    it('renders current step slot', () => {
        const wrapper = renderWizard();
        expect(wrapper.find('[data-test="body-a"]').exists()).toBe(true);
        expect(wrapper.find('[data-test="body-b"]').exists()).toBe(false);
    });

    it('emits update on forward navigation', async () => {
        const wrapper = renderWizard();
        const forwardBtn = wrapper
            .findAll('button.base-wizard__btn--primary')
            .at(0);
        expect(forwardBtn).toBeDefined();
        await forwardBtn!.trigger('click');
        expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['b']);
    });

    it('disables Back on first step', () => {
        const wrapper = renderWizard();
        const backBtn = wrapper.find('button.base-wizard__btn--secondary');
        expect(backBtn.attributes('disabled')).toBeDefined();
    });

    it('blocks forward when canProceed returns false', async () => {
        const wrapper = renderWizard({ canProceed: () => false });
        const primary = wrapper.find('button.base-wizard__btn--primary');
        expect(primary.attributes('disabled')).toBeDefined();
    });

    it('emits submit on last step', async () => {
        const wrapper = renderWizard({ modelValue: 'c' });
        const primary = wrapper.find('button.base-wizard__btn--primary');
        expect(primary.text()).toContain('Готово');
        await primary.trigger('click');
        expect(wrapper.emitted('submit')?.length).toBe(1);
    });

    it('hides steps where visible=false', () => {
        const wrapper = renderWizard({
            steps: [
                { id: 'a', title: 'Шаг A' },
                { id: 'b', title: 'Скрытый', visible: false },
                { id: 'c', title: 'Шаг C' },
            ],
        });
        const titles = wrapper
            .findAll('.base-wizard__progress-title')
            .map((node) => node.text());
        expect(titles).toEqual(['Шаг A', 'Шаг C']);
    });

    it('emits cancel via ghost button', async () => {
        const wrapper = renderWizard();
        const ghost = wrapper.find('button.base-wizard__btn--ghost');
        await ghost.trigger('click');
        expect(wrapper.emitted('cancel')?.length).toBe(1);
    });

    it('supports jumping to previously visited step via progress button', async () => {
        const wrapper = renderWizard({ modelValue: 'c' });
        const firstBtn = wrapper.find('.base-wizard__progress-btn');
        await firstBtn.trigger('click');
        expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['a']);
    });

    it('keeps modelValue if active step exists', async () => {
        const wrapper = renderWizard({ modelValue: 'b' });
        await wrapper.vm.$nextTick();
        expect(wrapper.emitted('update:modelValue')).toBeUndefined();
    });

    it('auto-falls-back to first visible step when modelValue not in visible set', async () => {
        const wrapper = renderWizard({
            modelValue: 'ghost',
            steps: [
                { id: 'a', title: 'Шаг A' },
                { id: 'b', title: 'Шаг B' },
            ],
        });
        await wrapper.vm.$nextTick();
        expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['a']);
    });
});
