export interface WizardStep {
    id: string;
    title: string;
    description?: string;
    visible?: boolean;
    required?: boolean;
    depends_on?: string[];
}

export interface WizardNavigationState {
    currentStep: string;
    currentIndex: number;
    total: number;
    visibleSteps: WizardStep[];
    canGoBack: boolean;
    canGoForward: boolean;
    isLast: boolean;
    isFirst: boolean;
}

export type CanProceedFn = (stepId: string) => boolean | { ok: false; reason: string };
