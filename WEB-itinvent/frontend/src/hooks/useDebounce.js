import { useState, useEffect } from 'react';

/**
 * Хук для откладывания обновления значения на заданное количество миллисекунд.
 * @param {any} value Значение, которое нужно отложить
 * @param {number} delay Задержка в мс
 * @returns {any} Отложенное значение
 */
function useDebounce(value, delay) {
    const [debouncedValue, setDebouncedValue] = useState(value);

    useEffect(() => {
        // Обновляем debouncedValue после задержки
        const handler = setTimeout(() => {
            setDebouncedValue(value);
        }, delay);

        // Отменяем таймаут, если value изменилось (также при размонтировании)
        // чтобы не срабатывал предыдущий таймаут
        return () => {
            clearTimeout(handler);
        };
    }, [value, delay]);

    return debouncedValue;
}

export default useDebounce;
