import './globals.css';
import './mobile-accessibility.css';
import './pass12-runtime.css';
import './pass13-accessibility.css';
import AppShell from '../components/AppShell';
import AccessibilityRuntime from '../components/AccessibilityRuntime';
import { CurrentUserProvider } from '../lib/useCurrentUser';

export const metadata = { title: 'POS Cloud' };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <CurrentUserProvider>
          <AccessibilityRuntime />
          <AppShell>{children}</AppShell>
        </CurrentUserProvider>
      </body>
    </html>
  );
}
