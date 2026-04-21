import type { Directive, DirectiveBinding } from 'vue';

type Handler = (event: MouseEvent) => void;

interface ClickOutsideElement extends HTMLElement {
    __clickOutsideHandler__?: (event: MouseEvent) => void;
}

export const clickOutside: Directive<ClickOutsideElement, Handler | undefined> = {
    mounted(el, binding: DirectiveBinding<Handler | undefined>) {
        const handler = (event: MouseEvent) => {
            if (!el.contains(event.target as Node) && typeof binding.value === 'function') {
                binding.value(event);
            }
        };
        el.__clickOutsideHandler__ = handler;
        document.addEventListener('mousedown', handler);
    },
    unmounted(el) {
        if (el.__clickOutsideHandler__) {
            document.removeEventListener('mousedown', el.__clickOutsideHandler__);
            delete el.__clickOutsideHandler__;
        }
    },
};
