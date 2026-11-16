import { createContext, useContext } from 'react';

export const PulseContext = createContext(null);
export function usePulse() {
  return useContext(PulseContext);
}
