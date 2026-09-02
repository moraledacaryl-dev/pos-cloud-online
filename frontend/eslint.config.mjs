import { defineConfig, globalIgnores } from 'eslint/config';
import nextVitals from 'eslint-config-next/core-web-vitals';

export default defineConfig([
  ...nextVitals,
  {
    rules: {
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/exhaustive-deps': 'off',
      'react-hooks/preserve-manual-memoization': 'off',
      '@next/next/no-location-assign-relative-destination': 'off',
      '@next/next/no-img-element': 'off',
    },
  },
  globalIgnores(['.next/**', 'node_modules/**', 'coverage/**']),
]);
