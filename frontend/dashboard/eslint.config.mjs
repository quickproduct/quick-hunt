import { defineConfig, globalIgnores } from 'eslint/config';
import nextVitals from 'eslint-config-next/core-web-vitals';

export default defineConfig([
  ...nextVitals,
  {
    // Existing pages intentionally start async data loads from mount effects.
    // React 19's new rule also flags the synchronous loading-state updates
    // inside those callbacks; migrating every screen requires a separate
    // data-layer refactor and is not a release-safety requirement.
    rules: {
      'react-hooks/set-state-in-effect': 'off',
    },
  },
  globalIgnores(['.next/**', 'out/**', 'build/**', 'next-env.d.ts']),
]);
