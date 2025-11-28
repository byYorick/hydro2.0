/**
 * Импорт функции route из Ziggy для использования в компонентах Vue
 * Функция route доступна глобально через @routes директиву в Blade шаблоне
 */
declare global {
  function route(name: string, params?: any, absolute?: boolean): string;
}

// Re-export для использования в компонентах
export function route(name: string, params?: any, absolute?: boolean): string {
  // Используем глобальную функцию route, созданную через @routes в Blade
  if (typeof window !== 'undefined' && typeof (window as any).route === 'function') {
    return (window as any).route(name, params, absolute);
  }
  
  // Fallback для SSR или если route еще не загружена
  throw new Error(`Route function not available. Make sure @routes directive is included in your Blade template.`);
}

