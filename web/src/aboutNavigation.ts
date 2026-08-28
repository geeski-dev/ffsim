import { createContext, useContext } from 'react';
import type { TooltipId } from './tooltips';

interface AboutNavigation {
  navigateToAbout(anchor?: TooltipId | string): void;
}

export const AboutNavigationContext = createContext<AboutNavigation | null>(null);

export function useAboutNavigation() {
  return useContext(AboutNavigationContext);
}
